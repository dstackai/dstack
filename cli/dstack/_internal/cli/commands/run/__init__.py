import argparse
import copy
import os
import sys
import threading
import time
from argparse import Namespace
from pathlib import Path
from typing import Dict, Iterator, List, Optional

import websocket
from cursor import cursor
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm
from rich.table import Table
from websocket import WebSocketApp

from dstack._internal.api.runs import list_runs_hub
from dstack._internal.backend.base.logs import fix_urls
from dstack._internal.cli.commands import BasicCommand
from dstack._internal.cli.commands.run.ssh_tunnel import PortsLock, run_ssh_tunnel
from dstack._internal.cli.commands.run.watcher import LocalCopier, SSHCopier, Watcher
from dstack._internal.cli.common import add_project_argument, check_init, console, print_runs
from dstack._internal.cli.config import config, get_hub_client
from dstack._internal.cli.configuration import load_configuration
from dstack._internal.core.error import RepoNotInitializedError
from dstack._internal.core.instance import InstanceType
from dstack._internal.core.job import Job, JobErrorCode, JobHead, JobStatus
from dstack._internal.core.plan import RunPlan
from dstack._internal.core.request import RequestStatus
from dstack._internal.core.run import RunHead
from dstack._internal.utils.ssh import (
    include_ssh_config,
    ssh_config_add_host,
    ssh_config_remove_host,
)
from dstack.api.hub import HubClient

POLL_PROVISION_RATE_SECS = 3

POLL_FINISHED_STATE_RATE_SECS = 1

interrupt_count = 0


class RunCommand(BasicCommand):
    NAME = "run"
    DESCRIPTION = "Run a configuration"

    def __init__(self, parser):
        super().__init__(parser, store_help=True)

    def register(self):
        self._parser.add_argument(
            "working_dir",
            metavar="WORKING_DIR",
            type=str,
            help="The working directory of the run",
        )
        self._parser.add_argument(
            "-f",
            "--file",
            metavar="FILE",
            help="The path to the run configuration file. Defaults to WORKING_DIR/.dstack.yml.",
            type=str,
            dest="file_name",
        )
        self._parser.add_argument(
            "-y",
            "--yes",
            help="Do not ask for plan confirmation",
            action="store_true",
        )
        self._parser.add_argument(
            "-d",
            "--detach",
            help="Do not poll logs and run status",
            action="store_true",
        )
        add_project_argument(self._parser)
        self._parser.add_argument(
            "--profile",
            metavar="PROFILE",
            help="The name of the profile",
            type=str,
            dest="profile_name",
        )
        self._parser.add_argument(
            "-t",
            "--tag",
            metavar="TAG",
            help="A tag name. Warning, if the tag exists, " "it will be overridden.",
            type=str,
            dest="tag_name",
        )
        self._parser.add_argument(
            "args",
            metavar="ARGS",
            nargs=argparse.ZERO_OR_MORE,
            help="Run arguments",
        )
        self._parser.add_argument(
            "--reload",
            action="store_true",
            help="Enable auto-reload",
        )

    @check_init
    def _command(self, args: Namespace):
        configurator = load_configuration(args.working_dir, args.file_name, args.profile_name)
        if args.help:
            configurator.get_parser(parser=copy.deepcopy(self._parser)).print_help()
            exit(0)

        project_name = None
        if args.project:
            project_name = args.project
        elif configurator.profile.project:
            project_name = configurator.profile.project

        watcher = Watcher(os.getcwd())
        try:
            if args.reload:
                watcher.start()
            hub_client = get_hub_client(project_name=project_name)
            if (
                hub_client.repo.repo_data.repo_type != "local"
                and not hub_client.get_repo_credentials()
            ):
                raise RepoNotInitializedError("No credentials", project_name=project_name)

            if not config.repo_user_config.ssh_key_path:
                ssh_key_pub = None
            else:
                ssh_key_pub = _read_ssh_key_pub(config.repo_user_config.ssh_key_path)

            configurator_args, run_args = configurator.get_parser().parse_known_args(
                args.args + args.unknown
            )
            configurator.apply_args(configurator_args)

            run_plan = hub_client.get_run_plan(configurator)
            console.print("dstack will execute the following plan:\n")
            _print_run_plan(configurator.configuration_path, run_plan)
            if not args.yes and not Confirm.ask("Continue?"):
                console.print("\nExiting...")
                exit(0)
            console.print("\nProvisioning...\n")

            run_name, jobs = hub_client.run_configuration(
                configurator=configurator,
                ssh_key_pub=ssh_key_pub,
                run_args=run_args,
            )
            runs = list_runs_hub(hub_client, run_name=run_name)
            run = runs[0]
            if not args.detach:
                _poll_run(
                    hub_client,
                    run,
                    jobs,
                    ssh_key=config.repo_user_config.ssh_key_path,
                    watcher=watcher,
                )
        finally:
            if watcher.is_alive():
                watcher.stop()
                watcher.join()


def _read_ssh_key_pub(key_path: str) -> str:
    path = Path(key_path)
    return path.with_suffix(path.suffix + ".pub").read_text().strip("\n")


def _print_run_plan(configuration_file: str, run_plan: RunPlan):
    table = Table(box=None)
    table.add_column("CONFIGURATION", style="grey58")
    table.add_column("USER", style="grey58", no_wrap=True, max_width=16)
    table.add_column("PROJECT", style="grey58", no_wrap=True, max_width=16)
    table.add_column("INSTANCE")
    table.add_column("RESOURCES")
    table.add_column("SPOT POLICY")
    table.add_column("BUILD")
    job_plan = run_plan.job_plans[0]
    instance = job_plan.instance_type.instance_name or "-"
    instance_info = _format_resources(job_plan.instance_type)
    spot = job_plan.job.spot_policy.value
    build_plan = job_plan.build_plan.value.title()
    table.add_row(
        configuration_file,
        run_plan.hub_user_name,
        run_plan.project,
        instance,
        instance_info,
        spot,
        build_plan,
    )
    console.print(table)
    console.print()


def _format_resources(instance_type: InstanceType) -> str:
    instance_info = ""
    instance_info += f"{instance_type.resources.cpus}xCPUs"
    instance_info += f", {instance_type.resources.memory_mib}MB"
    if instance_type.resources.gpus:
        instance_info += (
            f", {len(instance_type.resources.gpus)}x{instance_type.resources.gpus[0].name}"
        )
    return instance_info


def _poll_run(
    hub_client: HubClient,
    run: RunHead,
    job_heads: List[JobHead],
    ssh_key: Optional[str],
    watcher: Optional[Watcher],
):
    print_runs([run])
    console.print()
    if run.status == JobStatus.FAILED:
        _print_failed_run_message(run)
        exit(1)
    run_name = run.run_name

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
                hub_client, run_name, loop_statuses=[JobStatus.PENDING, JobStatus.SUBMITTED]
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

        # attach to the instance, attach to the container in the background
        jobs = [hub_client.get_job(job_head.job_id) for job_head in job_heads]
        ports = _attach(hub_client, jobs[0], ssh_key)
        console.print()
        console.print("[grey58]To stop, press Ctrl+C.[/]")
        console.print()

        run = hub_client.list_run_heads(run_name)[0]
        if run.status.is_unfinished() or run.status == JobStatus.DONE:
            if watcher is not None and watcher.is_alive():  # reload is enabled
                if hub_client.get_project_backend_type() == "local":
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
            _poll_logs_ws(hub_client, jobs[0], ports)
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
        ssh_config_remove_host(config.ssh_config_path, f"{run_name}-host")
        ssh_config_remove_host(config.ssh_config_path, run_name)
    except KeyboardInterrupt:
        global interrupt_count
        interrupt_count = 1
        _ask_on_interrupt(hub_client, run_name)


def _print_failed_run_message(run: RunHead):
    if run.job_heads[0].error_code is JobErrorCode.FAILED_TO_START_DUE_TO_NO_CAPACITY:
        console.print("Provisioning failed due to no capacity\n")
    elif run.job_heads[0].error_code is JobErrorCode.BUILD_NOT_FOUND:
        console.print("Build not found. Run `dstack build` or add `--build` flag")
    else:
        console.print("Provisioning failed\n")


def _attach(hub_client: HubClient, job: Job, ssh_key_path: str) -> Dict[int, int]:
    """
    :return: (host tunnel ports, container tunnel ports, ports mapping)
    """
    backend_type = hub_client.get_project_backend_type()
    app_ports = {}
    openssh_server_port = 0
    for app in job.app_specs or []:
        app_ports[app.port] = app.map_to_port or 0
        if app.app_name == "openssh-server":
            openssh_server_port = app.port
    if backend_type == "local" and openssh_server_port == 0:
        console.print("Provisioning... It may take up to a minute. [green]✓[/]")
        return {k: v for k, v in app_ports.items() if v != 0}

    console.print("Starting SSH tunnel...")
    include_ssh_config(config.ssh_config_path)
    ws_port = int(job.env["WS_LOGS_PORT"])
    host_ports = {ws_port: ws_port}

    if backend_type != "local":
        ssh_config_add_host(
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
                "ControlPersist": "10m",
            },
        )
        host_ports[ws_port] = 0  # to map dynamically
        if openssh_server_port == 0:
            host_ports.update(app_ports)
            app_ports = {}
        host_ports = PortsLock(host_ports).acquire().release()
        for i in range(3):  # retry
            time.sleep(2**i)
            if run_ssh_tunnel(f"{job.run_name}-host", host_ports):
                break
        else:
            console.print("[warning]Warning: failed to start SSH tunnel[/warning] [red]✗[/]")

    if openssh_server_port != 0:
        options = {
            "HostName": "localhost",
            "Port": app_ports[openssh_server_port] or openssh_server_port,
            "User": "root",
            "IdentityFile": ssh_key_path,
            "StrictHostKeyChecking": "no",
            "UserKnownHostsFile": "/dev/null",
            "ControlPath": config.ssh_control_path(job.run_name),
            "ControlMaster": "auto",
            "ControlPersist": "10m",
        }
        if backend_type != "local":
            options["ProxyJump"] = f"{job.run_name}-host"
        ssh_config_add_host(config.ssh_config_path, job.run_name, options)
        del app_ports[openssh_server_port]
        if app_ports:
            app_ports_lock = PortsLock(app_ports).acquire()
            app_ports = app_ports_lock.dict()
            # try to attach in the background
            threading.Thread(
                target=_attach_to_container,
                args=(hub_client, job.run_name, app_ports_lock),
                daemon=True,
            ).start()

    return {**host_ports, **app_ports}


def _attach_to_container(hub_client: HubClient, run_name: str, ports_lock: PortsLock):
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
        hub_client.stop_jobs(run_name, abort=True)
        exit(1)


def _poll_logs_ws(hub_client: HubClient, job: Job, ports: Dict[int, int]):
    def on_message(ws: WebSocketApp, message):
        message = fix_urls(message, job, ports, hostname="127.0.0.1")
        sys.stdout.buffer.write(message)
        sys.stdout.buffer.flush()

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
        run_heads = hub_client.list_run_heads(run_name)
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
                hub_client.stop_jobs(run_name, abort=False)
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
        hub_client.stop_jobs(run_name, abort=True)
        console.print("[grey58]Aborted[/]")
        ssh_config_remove_host(config.ssh_config_path, f"{run_name}-host")
        ssh_config_remove_host(config.ssh_config_path, run_name)
        exit(0)
