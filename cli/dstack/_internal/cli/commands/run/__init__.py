import argparse
import os
import sys
import time
from argparse import Namespace
from pathlib import Path
from typing import Dict, Iterator, List, Optional

import websocket
from cursor import cursor
from jsonschema import ValidationError
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm
from websocket import WebSocketApp

from dstack._internal import providers
from dstack._internal.backend.base.logs import fix_urls
from dstack._internal.cli.commands import BasicCommand
from dstack._internal.cli.commands.run.ssh_tunnel import allocate_local_ports, run_ssh_tunnel
from dstack._internal.cli.commands.run.watcher import LocalCopier, SSHCopier, Watcher
from dstack._internal.cli.common import add_project_argument, check_init, console, print_runs
from dstack._internal.cli.config import config, get_hub_client
from dstack._internal.core.error import NameNotFoundError, RepoNotInitializedError
from dstack._internal.core.job import Job, JobHead, JobStatus
from dstack._internal.core.request import RequestStatus
from dstack._internal.core.run import RunHead
from dstack._internal.utils.ssh import (
    include_ssh_config,
    ssh_config_add_host,
    ssh_config_remove_host,
)
from dstack._internal.utils.workflows import load_workflows
from dstack.api.hub import HubClient
from dstack.api.runs import list_runs

POLL_PROVISION_RATE_SECS = 3

POLL_FINISHED_STATE_RATE_SECS = 1

interrupt_count = 0


class RunCommand(BasicCommand):
    NAME = "run"
    DESCRIPTION = "Run a workflow"

    def __init__(self, parser):
        super(RunCommand, self).__init__(parser)

    def register(self):
        workflow_names = list(
            load_workflows(os.path.join(os.getcwd(), ".dstack")).keys()
        )  # todo use repo
        provider_names = providers.get_provider_names()
        workflow_or_provider_names = workflow_names + provider_names
        workflow_help = "{" + ",".join(workflow_or_provider_names) + "}"
        self._parser.add_argument(
            "workflow_or_provider",
            metavar="WORKFLOW",
            type=str,
            help=workflow_help,
            choices=workflow_or_provider_names,
            nargs="?",
        )
        add_project_argument(self._parser)
        self._parser.add_argument(
            "-t",
            "--tag",
            metavar="TAG",
            help="A tag name. Warning, if the tag exists, " "it will be overridden.",
            type=str,
            dest="tag_name",
        )
        self._parser.add_argument(
            "-d",
            "--detach",
            help="Do not poll for status update and logs",
            action="store_true",
        )
        self._parser.add_argument(
            "args",
            metavar="ARGS",
            nargs=argparse.ZERO_OR_MORE,
            help="Override workflow or provider arguments",
        )
        self._parser.add_argument(
            "--reload",
            action="store_true",
            help="Enable local changes one-directional synchronization",
        )

    @check_init
    def _command(self, args: Namespace):
        if not args.workflow_or_provider:
            self._parser.print_help()
            exit(1)
        watcher = Watcher(os.getcwd())
        try:
            if args.reload:
                watcher.start()
            hub_client = get_hub_client(project_name=args.project)
            if (
                hub_client.repo.repo_data.repo_type != "local"
                and not hub_client.get_repo_credentials()
            ):
                raise RepoNotInitializedError("No credentials", project_name=args.project)

            if not config.repo_user_config.ssh_key_path:
                ssh_pub_key = None
            else:
                ssh_pub_key = _read_ssh_key_pub(config.repo_user_config.ssh_key_path)

            try:
                run_name, jobs = hub_client.run_workflow(
                    args.workflow_or_provider,
                    ssh_pub_key=ssh_pub_key,
                    tag_name=args.tag_name,
                    args=args,
                )
            except NameNotFoundError:
                run_name, jobs = hub_client.run_provider(
                    args.workflow_or_provider,
                    ssh_pub_key=ssh_pub_key,
                    tag_name=args.tag_name,
                    args=args,
                )
            runs = list_runs(hub_client, run_name=run_name)
            print_runs(runs)
            run = runs[0]
            if run.status == JobStatus.FAILED:
                console.print("\nProvisioning failed\n")
                exit(1)
            if not args.detach:
                _poll_run(
                    hub_client,
                    jobs,
                    ssh_key=config.repo_user_config.ssh_key_path,
                    watcher=watcher,
                )
        except ValidationError as e:
            sys.exit(
                f"There a syntax error in one of the files inside the {os.getcwd()}/.dstack/workflows directory:\n\n{e}"
            )
        finally:
            if watcher.is_alive():
                watcher.stop()
                watcher.join()


def _read_ssh_key_pub(key_path: str) -> str:
    path = Path(key_path)
    return path.with_suffix(path.suffix + ".pub").read_text().strip("\n")


def _poll_run(
    hub_client: HubClient,
    job_heads: List[JobHead],
    ssh_key: Optional[str],
    watcher: Optional[Watcher],
):
    run_name = job_heads[0].run_name
    try:
        console.print()
        request_errors_printed = False
        downloading = False
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            SpinnerColumn(),
            transient=True,
        ) as progress:
            task = progress.add_task("Provisioning... It may take up to a minute.", total=None)
            for run in poll_run_head(hub_client, run_name):
                if run.status == JobStatus.DOWNLOADING and not downloading:
                    progress.update(task, description="Downloading deps... It may take a while.")
                    downloading = True
                elif run.status not in [JobStatus.SUBMITTED, JobStatus.DOWNLOADING]:
                    progress.update(task, total=100)
                    break
                if run.has_request_status([RequestStatus.TERMINATED, RequestStatus.NO_CAPACITY]):
                    if run.has_request_status([RequestStatus.TERMINATED]):
                        progress.update(
                            task,
                            description=f"[red]Request(s) terminated[/]",
                            total=100,
                        )
                        break
                    elif not request_errors_printed and run.has_request_status(
                        [RequestStatus.NO_CAPACITY]
                    ):
                        progress.update(task, description=f"[dark_orange]No capacity[/]")
                        request_errors_printed = True
                elif request_errors_printed:
                    progress.update(
                        task, description="Provisioning... It may take up to a minute."
                    )
                    request_errors_printed = False

        jobs = [hub_client.get_job(job_head.job_id) for job_head in job_heads]
        backend_type = hub_client.get_project_backend_type()
        ports = attach(
            hub_client,
            jobs[0],
            ssh_key,
        )
        console.print()
        console.print("[grey58]To exit, press Ctrl+C.[/]")
        console.print()

        run = hub_client.list_run_heads(run_name)[0]
        if run.status.is_unfinished() or run.status == JobStatus.DONE:
            if watcher.is_alive():  # reload is enabled
                if backend_type == "local":
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
        ask_on_interrupt(hub_client, run_name)

    try:
        uploading = False
        status = "unknown"
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            SpinnerColumn(),
            transient=True,
        ) as progress:
            task = progress.add_task("Stopping... To abort press Ctrl+C", total=None)
            for run in poll_run_head(hub_client, run_name):
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
        ask_on_interrupt(hub_client, run_name)


def _poll_logs_ws(hub_client: HubClient, job: Job, ports: Dict[int, int]):
    def on_message(ws: WebSocketApp, message):
        message = fix_urls(message, job, ports, hostname="127.0.0.1")
        sys.stdout.buffer.write(message)
        sys.stdout.buffer.flush()

    def on_error(_: WebSocketApp, err: Exception):
        if isinstance(err, KeyboardInterrupt):
            ask_on_interrupt(hub_client, job.run_name)
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
    if atty:
        cursor.show()


def poll_run_head(
    hub_client: HubClient, run_name: str, rate: int = POLL_PROVISION_RATE_SECS
) -> Iterator[RunHead]:
    while True:
        run_heads = hub_client.list_run_heads(run_name)
        if len(run_heads) == 0:
            continue
        run_head = run_heads[0]
        yield run_head
        time.sleep(rate)


def ask_on_interrupt(hub_client: HubClient, run_name: str):
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


def attach(hub_client: HubClient, job: Job, ssh_key_path: str) -> Dict[int, int]:
    backend_type = hub_client.get_project_backend_type()
    app_ports = {}
    openssh_server_port = 0
    for app in job.app_specs or []:
        app_ports[app.port] = app.map_to_port or 0
        if app.app_name == "openssh-server":
            openssh_server_port = app.port
    if not (backend_type != "local" or openssh_server_port != 0):
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
                "User": "root" if backend_type != "azure" else "ubuntu",
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
        host_ports = allocate_local_ports(host_ports)
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
            app_ports = allocate_local_ports(app_ports)
            for delay in range(0, 61, POLL_PROVISION_RATE_SECS):  # retry
                time.sleep(POLL_PROVISION_RATE_SECS if delay else 0)  # skip first sleep
                if run_ssh_tunnel(job.run_name, app_ports):
                    break
                run_status = hub_client.list_run_heads(job.run_name, repo_id=job.repo_ref.repo_id)[
                    0
                ].status
                if run_status != JobStatus.RUNNING:
                    break
            else:
                console.print(
                    "[red]ERROR[/] Can't establish SSH tunnel with the container\n"
                    "[grey58]Aborting...[/]"
                )
                hub_client.stop_jobs(job.run_name, abort=True)
                exit(1)
        console.print(f"To connect via SSH, use: `ssh {job.run_name}`")

    return {**host_ports, **app_ports}
