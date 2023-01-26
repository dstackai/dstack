import sys
import os
import time
import re

import yaml
import pkg_resources
import argparse
from argparse import Namespace
from jsonschema import validate, ValidationError
from pathlib import Path
from typing import List, Any, Tuple, Optional, Dict
from rich.console import Console
from rich.progress import SpinnerColumn, Progress, TextColumn
from rich.prompt import Confirm
from urllib import parse
from cursor import cursor
import websocket
from websocket import WebSocketApp


from dstack import providers
from dstack.core.error import check_config, check_git, check_backend
from dstack.core.repo import RepoAddress
from dstack.backend import Backend
from dstack.core.job import JobHead, JobStatus
from dstack.core.request import RequestStatus
from dstack.cli.commands import BasicCommand
from dstack.cli.commands.ps import print_runs, _has_request_status # TODO ugly
from dstack.api.repo import load_repo_data
from dstack.api.backend import get_backend_by_name, DEFAULT, DEFAULT_REMOTE
from dstack.api.logs import poll_logs
from dstack.util import since

__all__ = "RunCommand"

POLL_PROVISION_RATE_SECS = 3

POLL_FINISHED_STATE_RATE_SECS = 1


def _load_workflows_from_file(workflows_file: Path) -> List[Any]:
    workflows_yaml = yaml.load(workflows_file.open(), Loader=yaml.FullLoader)
    workflows_schema_yaml = pkg_resources.resource_string("dstack.schemas", "workflows.json")
    validate(workflows_yaml, yaml.load(workflows_schema_yaml, Loader=yaml.FullLoader))
    return workflows_yaml.get("workflows") or []


def _load_workflows():
    workflows = []
    root_folder = Path(os.getcwd()) / ".dstack"
    if root_folder.exists():
        workflows_file = root_folder / "workflows.yaml"
        if workflows_file.exists():
            workflows.extend(_load_workflows_from_file(workflows_file))
        workflows_dir = root_folder / "workflows"
        if workflows_dir.is_dir():
            for workflows_file in os.listdir(workflows_dir):
                workflows_file_path = workflows_dir / workflows_file
                if workflows_file_path.name.endswith(".yaml") or workflows_file_path.name.endswith(".yml"):
                    workflows.extend(_load_workflows_from_file(workflows_file_path))
    return workflows


def parse_run_args(args: Namespace) -> Tuple[str, List[str], Optional[str], Dict[str, Any]]:
    provider_args = args.args + args.unknown
    workflow_name = None
    workflow_data = {}

    workflows = _load_workflows()
    workflow_names = [w.get("name") for w in workflows]
    workflow_providers = {w.get("name"): w.get("provider") for w in workflows}

    if args.workflow_or_provider in workflow_names:
        workflow_name = args.workflow_or_provider
        workflow_data = next(w for w in workflows if w.get("name") == workflow_name)
        provider_name = workflow_providers[workflow_name]
    else:
        if args.workflow_or_provider not in providers.get_provider_names():
            sys.exit(f"No workflow or provider '{args.workflow_or_provider}' is found")

        provider_name = args.workflow_or_provider

    return provider_name, provider_args, workflow_name, workflow_data


def poll_logs_ws(backend: Backend, repo_address: RepoAddress,
                 job_head: JobHead, console):
    job = backend.get_job(repo_address, job_head.job_id)

    def on_message(ws: WebSocketApp, message):
        pat = re.compile(f'http://(localhost|0.0.0.0|127.0.0.1|{job.host_name}):[\\S]*[^(.+)\\s\\n\\r]')
        if re.search(pat, message):
            if job.host_name and job.ports and job.app_specs:
                for app_spec in job.app_specs:
                    port = job.ports[app_spec.port_index]
                    url_path = app_spec.url_path or ""
                    url_query_params = app_spec.url_query_params
                    url_query = ("?" + parse.urlencode(url_query_params)) if url_query_params else ""
                    app_url = f"http://{job.host_name}:{port}"
                    if url_path or url_query_params:
                        app_url += "/"
                        if url_query_params:
                            app_url += url_query
                    message = re.sub(pat, app_url, message)
        sys.stdout.write(message)

    def on_error(_: WebSocketApp, err: Exception):
        if isinstance(err, KeyboardInterrupt):
            run_name = job_head.run_name
            if Confirm.ask(f"\n [red]Abort the run '{run_name}'?[/]"):
                backend.stop_jobs(repo_address, run_name, abort=True)
                console.print(f"[grey58]OK[/]")
        else:
            print(str(err))

    def on_open(_: WebSocketApp):
        pass

    def on_close(_: WebSocketApp, close_status_code, close_msg):
        pass

    url = f"ws://{job.host_name}:{job.env['WS_LOGS_PORT']}/logsws"
    cursor.hide()
    _ws = websocket.WebSocketApp(url, on_message=on_message, on_error=on_error, on_open=on_open,
                                 on_close=on_close)
    _ws.run_forever()
    cursor.show()

    try:
        while True:
            _job_head = backend.get_job(repo_address, job_head.job_id)
            run = next(iter(backend.get_run_heads(repo_address,
                                                  [_job_head], include_request_heads=False)))
            if run.status.is_finished():
                break
            time.sleep(POLL_FINISHED_STATE_RATE_SECS)
    except KeyboardInterrupt:
        if Confirm.ask(f"\n [red]Abort the run '{job.run_name}'?[/]"):
            backend.stop_jobs(repo_address, job.run_name, abort=True)
            console.print(f"[grey58]OK[/]")


def poll_run(repo_address: RepoAddress, job_heads: List[JobHead], backend: Backend):
    console = Console()
    try:
        console.print()
        request_errors_printed = False
        downloading = False
        with Progress(TextColumn("[progress.description]{task.description}"), SpinnerColumn(),
                      transient=True, ) as progress:
            task = progress.add_task("Provisioning... It may take up to a minute.", total=None)
            while True:
                time.sleep(POLL_PROVISION_RATE_SECS)
                _job_heads = [backend.get_job(repo_address, job_head.job_id) for job_head in job_heads]
                run = next(iter(backend.get_run_heads(repo_address, _job_heads)))
                if run.status == JobStatus.DOWNLOADING and not downloading:
                    progress.update(task, description="Downloading deps... It may take a while.")
                    downloading = True
                elif run.status not in [JobStatus.SUBMITTED, JobStatus.DOWNLOADING]:
                    progress.update(task, total=100)
                    break
                if _has_request_status(run, [RequestStatus.TERMINATED, RequestStatus.NO_CAPACITY]):
                    if _has_request_status(run, [RequestStatus.TERMINATED]):
                        progress.update(task, description=f"[red]Request(s) terminated[/]", total=100)
                        break
                    elif not request_errors_printed and _has_request_status(run, [RequestStatus.NO_CAPACITY]):
                        progress.update(task, description=f"[dark_orange]No capacity[/]")
                        request_errors_printed = True
                elif request_errors_printed:
                    progress.update(task, description="Provisioning... It may take up to a minute.")
                    request_errors_printed = False
        console.print("Provisioning... It may take up to a minute. [green]✓[/]")
        console.print()
        console.print("[grey58]To interrupt, press Ctrl+C.[/]")
        console.print()
        if len(job_heads) == 1 and run and run.status == JobStatus.RUNNING:
            poll_logs_ws(backend, repo_address, job_heads[0], console)
        else:
            poll_logs(backend, repo_address, job_heads, since("1d"), attach=True, from_run=True)
    except KeyboardInterrupt:
        run_name = job_heads[0].run_name
        if Confirm.ask(f" [red]Abort the run '{run_name}'?[/]"):
            backend.stop_jobs(repo_address, run_name, abort=True)
            console.print(f"[grey58]OK[/]")


class RunCommand(BasicCommand):
    NAME = 'run'
    DESCRIPTION = 'Run a workflow'

    def __init__(self, parser):
        super(RunCommand, self).__init__(parser)

    def register(self):
        self._parser.add_argument("workflow_or_provider", metavar="WORKFLOW", type=str,
                                  help="A name of a workflow", nargs="?")
        self._parser.add_argument('--remote', metavar="BACKEND", nargs=argparse.ZERO_OR_MORE, help="", type=str)
        self._parser.add_argument("-t", "--tag", metavar="TAG", help="A tag name. Warning, if the tag exists, "
                                                                     "it will be overridden.", type=str,
                                  dest="tag_name")
        self._parser.add_argument("-d", "--detach", help="Do not poll for status update and logs", action="store_true")
        self._parser.add_argument("args", metavar="ARGS", nargs=argparse.ZERO_OR_MORE,
                                  help="Override provider arguments")
        # self._parser.add_argument('-h', '--help', action='store_true', default=argparse.SUPPRESS,
        # help='Show this help message and exit')

    @check_config
    @check_git
    @check_backend
    def _command(self, args: Namespace):
        if not args.workflow_or_provider:
            print("Usage: dstack run [-h] WORKFLOW [-d] [-l] [-t TAG] [OPTIONS ...] [ARGS ...]\n")
            workflows = _load_workflows()
            workflow_names = [w["name"] for w in workflows if w.get("name")]
            print(f'Positional arguments:\n'
                  f'  WORKFLOW              {{{",".join(workflow_names)}}}\n')
            print("Options:\n"
                  "  -t TAG, --tag TAG      A tag name. Warning, if the tag already exists, it will be overridden.\n"
                  "  -d, --detach           Do not poll for status update and logs\n"
                  "  -h, --help             Show this help output, or the help for a specified workflow or provider.\n")
            print("To see the help output for a particular workflow, use the following command:\n"
                  "  dstack run WORKFLOW --help")
        else:
            try:
                repo_data = load_repo_data()
                backend_name = DEFAULT
                if args.remote is not None:
                    if len(args.remote) == 0:
                        backend_name = DEFAULT_REMOTE
                    else:
                        backend_name = args.remote[0]
                backend = get_backend_by_name(backend_name)

                provider_name, provider_args, workflow_name, workflow_data = parse_run_args(args)
                provider = providers.load_provider(provider_name)
                if hasattr(args, "help") and args.help:
                    provider.help(workflow_name)
                    sys.exit()

                if backend.get_repo_credentials(repo_data):
                    run_name = backend.create_run(repo_data)
                    provider.load(backend, provider_args, workflow_name, workflow_data, run_name)
                    if args.tag_name:
                        tag_head = backend.get_tag_head(repo_data, args.tag_name)
                        if tag_head:
                            # if args.yes or Confirm.ask(f"[red]The tag '{args.tag_name}' already exists. "
                            #                            f"Do you want to override it?[/]"):
                            backend.delete_tag_head(repo_data, tag_head)
                            # else:
                            #     return
                    jobs = provider.submit_jobs(backend, args.tag_name)
                    backend.update_repo_last_run_at(repo_data, last_run_at=int(round(time.time() * 1000)))
                    print_runs(Namespace(run_name=run_name, all=False), backend)
                    if not args.detach:
                        poll_run(repo_data, jobs, backend)
                else:
                    sys.exit(f"Call 'dstack init' first")
            except ValidationError as e:
                sys.exit(
                    f"There a syntax error in one of the files inside the {os.getcwd()}/.dstack/workflows directory:\n\n{e}")
