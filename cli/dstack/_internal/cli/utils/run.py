import os
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional, Tuple

import websocket
from cursor import cursor
from rich.control import Control
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm
from rich.table import Table
from websocket import WebSocketApp

from dstack._internal.api.runs import list_runs_hub
from dstack._internal.backend.base.logs import fix_urls
from dstack._internal.cli.errors import CLIError
from dstack._internal.cli.utils.common import console, print_runs
from dstack._internal.cli.utils.config import config
from dstack._internal.cli.utils.ssh_tunnel import PortsLock, run_ssh_tunnel
from dstack._internal.cli.utils.watcher import LocalCopier, SSHCopier, Watcher
from dstack._internal.configurators import JobConfigurator
from dstack._internal.core.app import AppSpec
from dstack._internal.core.error import RepoNotInitializedError
from dstack._internal.core.instance import InstanceAvailability
from dstack._internal.core.job import ConfigurationType, Job, JobErrorCode, JobHead, JobStatus
from dstack._internal.core.plan import RunPlan
from dstack._internal.core.request import RequestStatus
from dstack._internal.core.run import RunHead
from dstack._internal.core.userconfig import RepoUserConfig
from dstack._internal.hub.schemas import RunInfo
from dstack._internal.utils.ssh import include_ssh_config, update_ssh_config
from dstack.api.hub import HubClient

POLL_PROVISION_RATE_SECS = 3

POLL_FINISHED_STATE_RATE_SECS = 1

interrupt_count = 0

# Set this env to run cloud runners locally
ENABLE_LOCAL_CLOUD = os.getenv("DSTACK_ENABLE_LOCAL_CLOUD") is not None


def read_ssh_key_pub(key_path: str) -> str:
    path = Path(key_path)
    return path.with_suffix(path.suffix + ".pub").read_text().strip("\n")


def print_run_plan(configurator: JobConfigurator, run_plan: RunPlan, candidates_limit: int = 3):
    job_plan = run_plan.job_plans[0]

    props = Table(box=None, show_header=False)
    props.add_column(no_wrap=True)  # key
    props.add_column()  # value

    req = job_plan.job.requirements
    if req.gpus:
        resources = pretty_format_resources(
            req.cpus,
            req.memory_mib / 1024,
            req.gpus.count,
            req.gpus.name,
            req.gpus.memory_mib / 1024 if req.gpus.memory_mib else None,
        )
    else:
        resources = pretty_format_resources(req.cpus, req.memory_mib / 1024)
    max_price = f"${req.max_price:g}" if req.max_price else "-"
    max_duration = f"{job_plan.job.max_duration / 3600:g}h" if job_plan.job.max_duration else "-"
    retry_policy = job_plan.job.retry_policy
    retry_policy = (
        (f"{retry_policy.limit / 3600:g}h" if retry_policy.limit else "yes")
        if retry_policy.retry
        else "no"
    )
    termination_policy = (
        job_plan.job.termination_policy.value if job_plan.job.termination_policy else "-"
    )

    def th(s: str) -> str:
        return f"[bold]{s}[/bold]"

    props.add_row(th("Configuration"), configurator.configuration_path)
    props.add_row(th("Project"), run_plan.project)
    props.add_row(th("User"), run_plan.hub_user_name)
    props.add_row(th("Min resources"), resources)
    props.add_row(th("Max price"), max_price)
    props.add_row(th("Max duration"), max_duration)
    props.add_row(th("Spot policy"), job_plan.job.spot_policy.value)
    props.add_row(th("Retry policy"), retry_policy)
    props.add_row(th("Termination policy"), termination_policy)

    candidates = Table(box=None)
    candidates.add_column("#")
    candidates.add_column("BACKEND")
    candidates.add_column("REGION")
    candidates.add_column("INSTANCE")
    candidates.add_column("RESOURCES")
    candidates.add_column("SPOT")
    candidates.add_column("PRICE")
    candidates.add_column()

    job_plan.candidates = job_plan.candidates[:candidates_limit]

    for i, c in enumerate(job_plan.candidates, start=1):
        r = c.instance.resources
        if r.gpus:
            resources = pretty_format_resources(
                r.cpus,
                r.memory_mib / 1024,
                len(r.gpus),
                r.gpus[0].name,
                r.gpus[0].memory_mib / 1024,
            )
        else:
            resources = pretty_format_resources(r.cpus, r.memory_mib / 1024)
        availability = ""
        if c.availability in {InstanceAvailability.NOT_AVAILABLE, InstanceAvailability.NO_QUOTA}:
            availability = c.availability.value.replace("_", " ").title()
        candidates.add_row(
            f"{i}",
            c.backend,
            c.region,
            c.instance.instance_name,
            resources,
            "yes" if r.spot else "no",
            f"${c.price:g}",
            availability,
            style=None if i == 1 else "grey58",
        )
    if len(job_plan.candidates) == candidates_limit:
        candidates.add_row("", "...", style="grey58")

    console.print(props)
    console.print()
    if len(job_plan.candidates) > 0:
        console.print(candidates)
        console.print()


def poll_run(
    hub_client: HubClient,
    run_info: RunInfo,
    job_heads: List[JobHead],
    ssh_key: Optional[str],
    watcher: Optional[Watcher],
    ports_locks: Tuple[PortsLock, PortsLock],
):
    print_runs([run_info])
    console.print()
    run = run_info.run_head
    if run.status == JobStatus.FAILED:
        _print_failed_run_message(run)
        exit(1)
    run_name = run.run_name

    printed_pending = False
    if run_info.run_head.status == JobStatus.PENDING:
        printed_pending = True

    try:
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            SpinnerColumn(),
            transient=True,
        ) as progress:
            task = None
            for run in _poll_run_head(hub_client, run_name, loop_statuses=[JobStatus.PENDING]):
                if task is None:
                    task = progress.add_task(
                        "Waiting for capacity... To exit, press Ctrl+C.", total=None
                    )

            if task is None:
                task = progress.add_task("Provisioning... It may take up to a minute.", total=None)

            # idle PENDING and SUBMITTED
            request_errors_printed = False
            for run in _poll_run_head(
                hub_client,
                run_name,
                loop_statuses=[JobStatus.PENDING, JobStatus.SUBMITTED, JobStatus.RESTARTING],
            ):
                if run.has_request_status([RequestStatus.NO_CAPACITY]):
                    if not request_errors_printed:
                        progress.update(task, description=f"[dark_orange]No capacity[/]")
                        request_errors_printed = True
                elif request_errors_printed:
                    progress.update(
                        task, description="Provisioning... It may take up to a minute."
                    )
                    request_errors_printed = False
            # handle TERMINATED and DOWNLOADING
            run = next(_poll_run_head(hub_client, run_name))
            if run.status == JobStatus.FAILED:
                console.print()
                _print_failed_run_message(run)
                exit(1)
            if run.status == JobStatus.DOWNLOADING:
                progress.update(task, description="Downloading deps... It may take a while.")
            elif run.has_request_status([RequestStatus.TERMINATED]):
                progress.update(
                    task,
                    total=100,
                    description=f"[red]Request(s) terminated[/]",
                )
            # idle DOWNLOADING
            for run in _poll_run_head(hub_client, run_name, loop_statuses=[JobStatus.DOWNLOADING]):
                pass
            progress.update(task, total=100)

        run_info = hub_client.list_runs(run_name)[0]
        run = run_info.run_head

        if printed_pending:
            console.control(Control.move(0, -3))
            print_runs([run_info])
            console.print()

        # attach to the instance, attach to the container in the background
        jobs = [hub_client.get_job(job_head.job_id) for job_head in job_heads]
        console.print("Starting SSH tunnel...")
        ports = _attach(hub_client, run_info, jobs[0], ssh_key, ports_locks)
        console.print()
        console.print("[grey58]To stop, press Ctrl+C.[/]")
        console.print()

        if run.status.is_unfinished() or run.status == JobStatus.DONE:
            if watcher is not None and watcher.is_alive():  # reload is enabled
                if run_info.backend == "local":
                    watcher.start_copier(
                        LocalCopier,
                        dst_root=os.path.expanduser(
                            f"~/.dstack/local_backend/{hub_client.project}/tmp/runs/{run_name}/{jobs[0].job_id}"
                        ),
                    )
                else:
                    watcher.start_copier(
                        SSHCopier,
                        ssh_host=f"{run_name}-host",
                        dst_root=f".dstack/tmp/runs/{run_name}/{jobs[0].job_id}",
                    )

            def log_handler(message: bytes):
                sys.stdout.buffer.write(message)
                sys.stdout.buffer.flush()

            _poll_logs_ws(hub_client, jobs[0], ports, log_handler)
    except KeyboardInterrupt:
        _ask_on_interrupt(hub_client, run_name)

    try:
        uploading = False
        status = "unknown"
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            SpinnerColumn(),
            transient=True,
        ) as progress:
            task = progress.add_task("Stopping... To abort press Ctrl+C", total=None)
            for run in _poll_run_head(hub_client, run_name):
                if run.status == JobStatus.UPLOADING and not uploading:
                    progress.update(
                        task, description="Uploading artifacts and cache... To abort press Ctrl+C"
                    )
                    uploading = True
                elif run.status.is_finished():
                    progress.update(task, total=100)
                    status = run.status.name
                    break
        console.print(f"[grey58]{status.capitalize()}[/]")
        _detach(run_name)
    except KeyboardInterrupt:
        global interrupt_count
        interrupt_count = 1
        _ask_on_interrupt(hub_client, run_name)


def _detach(run_name):
    update_ssh_config(config.ssh_config_path, f"{run_name}-host")
    update_ssh_config(config.ssh_config_path, run_name)


def _print_failed_run_message(run: RunHead):
    if run.job_heads[0].error_code is JobErrorCode.FAILED_TO_START_DUE_TO_NO_CAPACITY:
        console.print("Provisioning failed due to no capacity\n")
    elif run.job_heads[0].error_code is JobErrorCode.BUILD_NOT_FOUND:
        console.print("Build not found. Run `dstack build` or add `--build` flag")
    else:
        console.print(
            f"Provisioning failed.\nTo see runner logs, run `dstack logs --diagnose {run.run_name}`.\n"
        )


def reserve_ports(apps: List[AppSpec], local_backend: bool) -> Tuple[PortsLock, PortsLock]:
    """
    :return: host_ports_lock, app_ports_lock
    """
    app_ports = {app.port: app.map_to_port or 0 for app in apps}
    ssh_server_port = get_ssh_server_port(apps)

    if not local_backend and ssh_server_port is None:
        # cloud backend without ssh in the container: use a host ssh tunnel
        return PortsLock(app_ports).acquire(), PortsLock()

    if ssh_server_port is not None:
        # any backend with ssh in the container: use a container ssh tunnel
        del app_ports[ssh_server_port]
        # for cloud backend: using ProxyJump to access ssh in the container, no host port forwarding needed
        # for local backend: the same host, no port forwarding needed
        return PortsLock(), PortsLock(app_ports).acquire()

    # local backend without ssh in the container: all ports mapped by runner
    return PortsLock(), PortsLock()


def _attach(
    hub_client: HubClient,
    run_info: RunInfo,
    job: Job,
    ssh_key_path: str,
    ports_locks: Tuple[PortsLock, PortsLock],
) -> Dict[int, int]:
    """
    :return: ports_mapping
    """
    backend_type = run_info.backend
    app_ports = {app.port: app.map_to_port or 0 for app in job.app_specs or []}
    host_ports = {}
    ssh_server_port = get_ssh_server_port(job.app_specs or [])

    if backend_type == "local" and ssh_server_port is None:
        console.print("Provisioning... It may take up to a minute. [green]✓[/]")
        # local backend without ssh in container: all ports mapped by runner
        return {k: v for k, v in app_ports.items() if v != 0}

    include_ssh_config(config.ssh_config_path)

    host_ports_lock, app_ports_lock = ports_locks

    if backend_type != "local" and not ENABLE_LOCAL_CLOUD:
        # cloud backend, need to forward logs websocket
        if ssh_server_port is None:
            # ssh in the container: no need to forward app ports
            app_ports = {}
        host_ports = _run_host_ssh_tunnel(job, ssh_key_path, host_ports_lock, backend_type)

    if ssh_server_port is not None:
        # ssh in the container: update ssh config, run tunnel if any apps
        options = {
            "HostName": "localhost",
            "Port": app_ports[ssh_server_port] or ssh_server_port,
            "User": "root",
            "IdentityFile": ssh_key_path,
            "StrictHostKeyChecking": "no",
            "UserKnownHostsFile": "/dev/null",
            "ControlPath": config.ssh_control_path(job.run_name),
            "ControlMaster": "auto",
            "ControlPersist": "yes",
        }
        if backend_type != "local" and not ENABLE_LOCAL_CLOUD:
            options["ProxyJump"] = f"{job.run_name}-host"
        update_ssh_config(config.ssh_config_path, job.run_name, options)
        del app_ports[ssh_server_port]
        if app_ports:
            # save mapping, but don't release ports yet
            app_ports.update(app_ports_lock.dict())
            # try to attach in the background
            threading.Thread(
                target=_run_container_ssh_tunnel,
                args=(hub_client, job.run_name, app_ports_lock),
                daemon=True,
            ).start()

    return {**host_ports, **app_ports}


def _run_host_ssh_tunnel(
    job: Job, ssh_key_path: str, ports_lock: PortsLock, backend_type: str
) -> Dict[int, int]:
    update_ssh_config(
        config.ssh_config_path,
        f"{job.run_name}-host",
        {
            "HostName": job.host_name,
            # TODO: use non-root for all backends
            "User": "ubuntu" if backend_type in ("azure", "gcp", "lambda") else "root",
            "IdentityFile": ssh_key_path,
            "StrictHostKeyChecking": "no",
            "UserKnownHostsFile": "/dev/null",
            "ControlPath": config.ssh_control_path(f"{job.run_name}-host"),
            "ControlMaster": "auto",
            "ControlPersist": "yes",
        },
    )
    # get free port for logs
    host_ports = PortsLock({int(job.env["WS_LOGS_PORT"]): 0}).acquire().release()
    host_ports.update(ports_lock.release())
    for i in range(3):  # retry
        time.sleep(2**i)
        if run_ssh_tunnel(f"{job.run_name}-host", host_ports):
            break
    else:
        console.print("[warning]Warning: failed to start SSH tunnel[/warning] [red]✗[/]")
    return host_ports


def _run_container_ssh_tunnel(hub_client: HubClient, run_name: str, ports_lock: PortsLock):
    # idle BUILDING
    for run in _poll_run_head(hub_client, run_name, loop_statuses=[JobStatus.BUILDING]):
        pass
    app_ports = ports_lock.release()
    for delay in range(0, 60 * 10 + 1, POLL_PROVISION_RATE_SECS):  # retry
        time.sleep(POLL_PROVISION_RATE_SECS if delay else 0)  # skip first sleep
        if run_ssh_tunnel(run_name, app_ports):
            # console.print(f"To connect via SSH, use: `ssh {run_name}`")
            break
        if next(_poll_run_head(hub_client, run_name)).status != JobStatus.RUNNING:
            break
    else:
        console.print(
            "[red]ERROR[/] Can't establish SSH tunnel with the container\n"
            "[grey58]Aborting...[/]"
        )
        hub_client.stop_run(run_name, terminate=True, abort=True)
        exit(1)


def _poll_logs_ws(
    hub_client: HubClient, job: Job, ports: Dict[int, int], log_handler: Callable[[bytes], None]
):
    hostname = "127.0.0.1"
    secure = False
    if job.configuration_type == ConfigurationType.SERVICE:
        hostname = job.gateway.hostname
        secure = job.gateway.secure
        ports = {**ports, job.gateway.service_port: job.gateway.public_port}

    def on_message(ws: WebSocketApp, message):
        message = fix_urls(message, job, ports, hostname=hostname, secure=secure)
        log_handler(message)

    def on_error(_: WebSocketApp, err: Exception):
        if isinstance(err, KeyboardInterrupt):
            _ask_on_interrupt(hub_client, job.run_name)
        else:
            console.print(err)

    def on_open(_: WebSocketApp):
        pass

    def on_close(_: WebSocketApp, close_status_code, close_msg):
        pass

    local_ws_logs_port = ports.get(int(job.env["WS_LOGS_PORT"]), int(job.env["WS_LOGS_PORT"]))
    url = f"ws://127.0.0.1:{local_ws_logs_port}/logsws"
    atty = sys.stdout.isatty()
    if atty:
        cursor.hide()
    _ws = websocket.WebSocketApp(
        url,
        on_message=on_message,
        on_error=on_error,
        on_open=on_open,
        on_close=on_close,
    )
    try:
        _ws.run_forever()
    except KeyboardInterrupt:
        pass  # on_error() has already handled an error, but it raises here too
    finally:
        if atty:
            cursor.show()


def _poll_run_head(
    hub_client: HubClient,
    run_name: str,
    rate: int = POLL_PROVISION_RATE_SECS,
    loop_statuses: Optional[List[JobStatus]] = None,
) -> Iterator[RunHead]:
    while True:
        run_infos = hub_client.list_runs(run_name)
        run_heads = [r.run_head for r in run_infos]
        if len(run_heads) == 0:
            time.sleep(rate / 2)
            continue
        run_head = run_heads[0]
        if loop_statuses is not None and run_head.status not in loop_statuses:
            return
        yield run_head
        time.sleep(rate)


def _ask_on_interrupt(hub_client: HubClient, run_name: str):
    global interrupt_count
    if interrupt_count == 0:
        try:
            console.print("\n")
            if Confirm.ask(f"[red]Stop the run '{run_name}'?[/]"):
                interrupt_count += 1
                hub_client.stop_run(run_name, terminate=False, abort=False)
                console.print("\n[grey58]Stopping... To abort press Ctrl+C[/]", end="")
            else:
                console.print("\n[grey58]Detaching...[/]")
                console.print("[grey58]OK[/]")
                exit(0)
            return
        except KeyboardInterrupt:
            interrupt_count += 1
    if interrupt_count > 0:
        console.print("\n[grey58]Aborting...[/]")
        hub_client.stop_run(run_name, terminate=False, abort=True)
        console.print("[grey58]Aborted[/]")
        update_ssh_config(config.ssh_config_path, f"{run_name}-host")
        update_ssh_config(config.ssh_config_path, run_name)
        exit(0)


def get_ssh_server_port(apps: List[AppSpec]) -> Optional[int]:
    for app in apps:
        if app.app_name == "openssh-server":
            return app.port
    return None


def pretty_format_resources(
    cpu: int,
    memory: float,
    gpu_count: Optional[int] = None,
    gpu_name: Optional[str] = None,
    gpu_memory: Optional[float] = None,
) -> str:
    s = f"{cpu}xCPUs, {memory:g}GB"
    if gpu_count:
        s += f", {gpu_count}x{gpu_name or 'GPU'}"
        if gpu_memory:
            s += f" ({gpu_memory:g}GB)"
    return s


def get_run_plan(
    hub_client: HubClient,
    configurator: JobConfigurator,
    run_name: Optional[str] = None,
) -> RunPlan:
    if hub_client.repo.repo_data.repo_type != "local" and not hub_client.get_repo_credentials():
        raise RepoNotInitializedError("No credentials", project_name=hub_client.project)

    if run_name:
        _check_run_name(hub_client, run_name, True)

    return hub_client.get_run_plan(configurator)


def run_configuration(
    hub_client: HubClient,
    configurator: JobConfigurator,
    run_name: Optional[str],
    run_plan: RunPlan,
    verify_ports: bool,
    run_args: List[str],
    repo_user_config: RepoUserConfig,
) -> Tuple[str, List[Job], Optional[Tuple[PortsLock, PortsLock]]]:
    ports_locks = None
    if verify_ports:
        ports_locks = reserve_ports(
            apps=configurator.app_specs(),
            local_backend=run_plan.local_backend,
        )

    if not repo_user_config.ssh_key_path:
        ssh_key_pub = None
    else:
        ssh_key_pub = read_ssh_key_pub(repo_user_config.ssh_key_path)

    run_name, jobs = hub_client.run_configuration(
        configurator=configurator,
        ssh_key_pub=ssh_key_pub,
        run_name=run_name,
        run_args=run_args,
        run_plan=run_plan,
    )

    return run_name, jobs, ports_locks


def _check_run_name(hub_client: HubClient, run_name: str, auto_delete: bool):
    runs = list_runs_hub(hub_client, run_name=run_name)
    if len(runs) == 0:
        return
    elif auto_delete and runs[0].run_head.status.is_unfinished():
        raise CLIError("The run with this name is unfinished.")
    elif auto_delete and runs[0].run_head.status.is_finished():
        hub_client.delete_run(run_name)
    else:
        raise CLIError(
            "The run with this name already exists. Delete the run first with `dstack rm`."
        )
