import argparse
import os
import sys
import time
from argparse import Namespace
from pathlib import Path
from typing import Dict, List, Optional

import websocket
from cursor import cursor
from jsonschema import ValidationError
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm
from websocket import WebSocketApp

from dstack import providers
from dstack.api.hub import HubClient
from dstack.api.runs import list_runs
from dstack.backend.base.logs import fix_urls
from dstack.cli.commands import BasicCommand
from dstack.cli.commands.run.ssh_tunnel import allocate_local_ports, run_ssh_tunnel
from dstack.cli.common import check_init, console, print_runs
from dstack.cli.config import config, get_hub_client
from dstack.core.error import NameNotFoundError, RepoNotInitializedError
from dstack.core.job import Job, JobHead, JobStatus
from dstack.core.request import RequestStatus
from dstack.utils.workflows import load_workflows

POLL_PROVISION_RATE_SECS = 3

POLL_FINISHED_STATE_RATE_SECS = 1


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
            metavar="WORKFLOW | PROVIDER",
            type=str,
            help=workflow_help,
            choices=workflow_or_provider_names,
            nargs="?",
        )
        self._parser.add_argument(
            "--project",
            type=str,
            help="Hub project to execute the command",
            default=None,
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

    @check_init
    def _command(self, args: Namespace):
        if not args.workflow_or_provider:
            self._parser.print_help()
            exit(1)
        try:
            hub_client = get_hub_client(project_name=args.project)
            if not hub_client.get_repo_credentials():
                raise RepoNotInitializedError("No credentials")

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
                openssh_server = any(
                    spec.app_name == "openssh-server" for spec in jobs[0].app_specs or []
                )
                _poll_run(
                    hub_client,
                    jobs,
                    ssh_key=config.repo_user_config.ssh_key_path,
                    openssh_server=openssh_server,
                )
        except ValidationError as e:
            sys.exit(
                f"There a syntax error in one of the files inside the {os.getcwd()}/.dstack/workflows directory:\n\n{e}"
            )


def _read_ssh_key_pub(key_path: str) -> str:
    path = Path(key_path)
    return path.with_suffix(path.suffix + ".pub").read_text().strip("\n")


def _poll_run(
    hub_client: HubClient,
    job_heads: List[JobHead],
    ssh_key: Optional[str],
    openssh_server: bool,
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
            while True:
                time.sleep(POLL_PROVISION_RATE_SECS)
                run_heads = hub_client.list_run_heads(run_name)
                if len(run_heads) == 0:
                    continue
                run = run_heads[0]
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

        ports = {}
        jobs = [hub_client.get_job(job_head.job_id) for job_head in job_heads]
        if hub_client.get_project_backend_type() != "local":
            console.print("Starting SSH tunnel...")
            ports = allocate_local_ports(jobs)
            if not run_ssh_tunnel(
                ssh_key, jobs[0].host_name, ports
            ):  # todo: cleanup explicitly (stop tunnel)
                console.print("[warning]Warning: failed to start SSH tunnel[/warning] [red]✗[/]")
        else:
            console.print("Provisioning... It may take up to a minute. [green]✓[/]")
        console.print()
        console.print("[grey58]To interrupt, press Ctrl+C.[/]")
        console.print()

        if openssh_server:
            ssh_port = jobs[0].ports[-1]
            ssh_port = ports.get(ssh_port, ssh_port)
            ssh_key_escaped = ssh_key.replace(" ", "\\ ")
            console.print("To connect via SSH, use:")
            console.print(f"  ssh -i {ssh_key_escaped} root@localhost -p {ssh_port}")
            console.print()

        run = hub_client.list_run_heads(run_name)[0]
        if run.status.is_unfinished() or run.status == JobStatus.DONE:
            _poll_logs_ws(hub_client, jobs[0], ports)
    except KeyboardInterrupt:
        if Confirm.ask(f" [red]Abort the run '{run_name}'?[/]"):
            hub_client.stop_jobs(run_name, abort=True)
            console.print(f"[grey58]OK[/]")


def _poll_logs_ws(hub_client: HubClient, job: Job, ports: Dict[int, int]):
    def on_message(ws: WebSocketApp, message):
        message = fix_urls(message, job, ports, hostname="127.0.0.1")
        sys.stdout.buffer.write(message)
        sys.stdout.buffer.flush()

    def on_error(_: WebSocketApp, err: Exception):
        if isinstance(err, KeyboardInterrupt):
            run_name = job.run_name
            if Confirm.ask(f"\n [red]Abort the run '{run_name}'?[/]"):
                hub_client.stop_jobs(run_name, abort=True)
                console.print(f"[grey58]OK[/]")
            exit()
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
    _ws.run_forever()
    if atty:
        cursor.show()

    try:
        while True:
            _job_head = hub_client.get_job(job.job_id)
            run = hub_client.list_run_heads(_job_head.run_name)[0]
            if run.status.is_finished():
                break
            time.sleep(POLL_FINISHED_STATE_RATE_SECS)
    except KeyboardInterrupt:
        if Confirm.ask(f"\n [red]Abort the run '{job.run_name}'?[/]"):
            hub_client.stop_jobs(job.run_name, abort=True)
            console.print(f"[grey58]OK[/]")
