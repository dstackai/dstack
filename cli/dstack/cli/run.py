import argparse
import os
import re
import sys
import time
from argparse import Namespace
from pathlib import Path
from typing import List, Optional, Dict, Tuple, Any
from urllib import parse

import websocket
import yaml
from cursor import cursor
from git import InvalidGitRepositoryError
from jsonschema import validate, ValidationError
from rich.console import Console
from rich.progress import SpinnerColumn, Progress, TextColumn
from rich.prompt import Confirm
from websocket import WebSocketApp

from dstack import providers
from dstack.backend import load_backend, Backend, RequestStatus
from dstack.cli.logs import poll_logs, since
from dstack.cli.schema import workflows_schema_yaml
from dstack.cli.status import status_func, _has_request_status
from dstack.config import ConfigError
from dstack.jobs import JobStatus, JobHead
from dstack.repo import load_repo_data

POLL_PROVISION_RATE_SECS = 3


def _load_workflows():
    root_folder = Path(os.getcwd()) / ".dstack"
    if root_folder.exists():
        workflows_file = root_folder / "workflows.yaml"
        if workflows_file.exists():
            return yaml.load(workflows_file.open(), Loader=yaml.FullLoader)
        else:
            return None
    else:
        return None


def parse_run_args(args: Namespace) -> Tuple[str, List[str], Optional[str], Dict[str, Any]]:
    provider_args = args.args + args.unknown
    workflow_name = None
    workflow_data = {}

    workflows_yaml = _load_workflows()
    workflows = (workflows_yaml.get("workflows") or []) if workflows_yaml is not None else []
    if workflows:
        validate(workflows_yaml, yaml.load(workflows_schema_yaml, Loader=yaml.FullLoader))
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


def poll_run(repo_user_name: str, repo_name: str, job_heads: List[JobHead], backend: Backend):
    console = Console()
    try:
        console.print()
        request_errors_printed = False
        downloading = False
        run = None
        with Progress(TextColumn("[progress.description]{task.description}"), SpinnerColumn(),
                      transient=True, ) as progress:
            task = progress.add_task("Provisioning... It may take up to a minute.", total=None)
            while True:
                time.sleep(POLL_PROVISION_RATE_SECS)
                _job_heads = [backend.get_job(repo_user_name, repo_name, job_head.job_id) for job_head in job_heads]
                run = next(iter(backend.get_run_heads(repo_user_name, repo_name, _job_heads)))
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
            poll_logs_ws(backend, repo_user_name, repo_name, job_heads[0], console)
        else:
            poll_logs(backend, repo_user_name, repo_name, job_heads, since("1d"), attach=True, from_run=True)
    except KeyboardInterrupt:
        run_name = job_heads[0].run_name
        if Confirm.ask(f" [red]Abort the run '{run_name}'?[/]"):
            backend.stop_jobs(repo_user_name, repo_name, run_name, abort=True)
            console.print(f"[grey58]OK[/]")


def poll_logs_ws(backend: Backend, repo_user_name: str, repo_name: str,
                 job_head: JobHead, console):
    job = backend.get_job(repo_user_name, repo_name, job_head.job_id)

    def on_message(ws: WebSocketApp, message):
        pat = re.compile(f'http://(localhost|0.0.0.0|{job.host_name}):[\\S]*[^(.+)\\s\\n\\r]')
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

    def on_error(ws: WebSocketApp, err: Exception):
        if isinstance(err, KeyboardInterrupt):
            run_name = job_head.run_name
            if Confirm.ask(f"\n [red]Abort the run '{run_name}'?[/]"):
                backend.stop_jobs(repo_user_name, repo_name, run_name, abort=True)
                console.print(f"[grey58]OK[/]")
        else:
            pass

    def on_open(ws: WebSocketApp):
        pass

    def on_close(ws: WebSocketApp, close_status_code, close_msg):
        pass

    url = f"ws://{job.host_name}:4000/logsws"
    cursor.hide()
    ws = websocket.WebSocketApp(url, on_message=on_message, on_error=on_error, on_open=on_open,
                                on_close=on_close)
    ws.run_forever()
    cursor.show()


def run_workflow_func(args: Namespace):
    if not args.workflow_or_provider:
        print("Usage: dstack run [-h] WORKFLOW [-d] [-t TAG] [ARGS ...]\n")
        workflows_yaml = _load_workflows()
        workflows = (workflows_yaml or {}).get("workflows") or []
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
            backend = load_backend()

            provider_name, provider_args, workflow_name, workflow_data = parse_run_args(args)

            provider = providers.load_provider(provider_name)

            if hasattr(args, "help") and args.help:
                provider.help(workflow_name)
                sys.exit()

            provider.load(provider_args, workflow_name, workflow_data)
            if args.tag_name:
                tag_head = backend.get_tag_head(repo_data.repo_user_name, repo_data.repo_name, args.tag_name)
                if tag_head:
                    # if args.yes or Confirm.ask(f"[red]The tag '{args.tag_name}' already exists. "
                    #                            f"Do you want to override it?[/]"):
                    backend.delete_tag_head(repo_data.repo_user_name, repo_data.repo_name, tag_head)
                    # else:
                    #     return
            run_name = backend.create_run(repo_data.repo_user_name, repo_data.repo_name)
            jobs = provider.submit_jobs(run_name, args.tag_name)
            backend.update_repo_last_run_at(repo_data.repo_user_name, repo_data.repo_name,
                                            last_run_at=int(round(time.time() * 1000)))
            status_func(Namespace(run_name=run_name, all=False))
            if not args.detach:
                poll_run(repo_data.repo_user_name, repo_data.repo_name, jobs, backend)

        except ConfigError:
            sys.exit(f"Call 'dstack config' first")
        except InvalidGitRepositoryError:
            sys.exit(f"{os.getcwd()} is not a Git repo")
        except ValidationError as e:
            sys.exit(f"There a syntax error in {os.getcwd()}/.dstack/workflows.yaml:\n\n{e}")


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("run", help="Run a workflow", add_help=False)
    parser.add_argument("workflow_or_provider", metavar="WORKFLOW", type=str,
                        help="A name of a workflow", nargs="?")
    parser.add_argument("-t", "--tag", metavar="TAG", help="A tag name. Warning, if the tag exists, "
                                                           "it will be overridden.", type=str, dest="tag_name")
    parser.add_argument("-d", "--detach", help="Do not poll for status update and logs", action="store_true")
    # parser.add_argument("-y", "--yes", help="Don't ask for confirmation", action="store_true")
    parser.add_argument("args", metavar="ARGS", nargs=argparse.ZERO_OR_MORE, help="Override provider arguments")
    parser.add_argument('-h', '--help', action='store_true', default=argparse.SUPPRESS,
                        help='Show this help message and exit')

    parser.set_defaults(func=run_workflow_func)
