import argparse
import os
import sys
import time
from argparse import Namespace
from pathlib import Path
from typing import List, Optional, Dict, Tuple, Any

import yaml
from git import InvalidGitRepositoryError
from jsonschema import validate, ValidationError
from rich.console import Console
from rich.progress import SpinnerColumn, Progress, TextColumn
from rich.prompt import Confirm

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
            sys.exit(f"No workflow or provider `{args.workflow_or_provider}` is found")

        provider_name = args.workflow_or_provider

    return provider_name, provider_args, workflow_name, workflow_data


def poll_run(repo_user_name: str, repo_name: str, job_heads: List[JobHead], backend: Backend):
    console = Console()
    try:
        console.print()
        request_errors_printed = False
        with Progress(TextColumn("[progress.description]{task.description}"), SpinnerColumn(),
                      transient=True, ) as progress:
            task = progress.add_task("Provisioning... It may take up to a minute.", total=None)
            while True:
                run = next(iter(backend.get_run_heads(repo_user_name, repo_name, job_heads)))
                if run.status.is_finished():
                    sys.exit(0)
                elif run.status not in [JobStatus.SUBMITTED]:
                    progress.update(task, total=100)
                    break
                if _has_request_status(run, [RequestStatus.TERMINATED, RequestStatus.NO_CAPACITY]):
                    if _has_request_status(run, [RequestStatus.TERMINATED]):
                        progress.update(task, description=f"[red]Request(s) terminated[/]", total=100)
                        break
                    elif not request_errors_printed and _has_request_status(run, [RequestStatus.NO_CAPACITY]):
                        progress.update(task, description=f"[dark_orange]No capacity")
                        request_errors_printed = True
                elif request_errors_printed:
                    progress.update(task, description="Provisioning... It may take up to a minute.")
                    request_errors_printed = False
                time.sleep(POLL_PROVISION_RATE_SECS)
        console.print("Provisioning... It may take up to a minute. [green]✓[/]")
        console.print()
        console.print("[grey58]To interrupt, press Ctrl+C.[/]")
        console.print()
        poll_logs(backend, repo_user_name, repo_name, job_heads, since("1d"), follow=True, from_run=True)
    except KeyboardInterrupt:
        run_name = job_heads[0].run_name
        if Confirm.ask(f" [red]Stop the run '{run_name}'?[/]"):
            backend.stop_jobs(repo_user_name, repo_name, run_name, abort=True)
            console.print(f"[grey58]OK[/]")


def run_workflow_func(args: Namespace):
    if not args.workflow_or_provider:
        print("Usage: dstack run [-d] [-h] (WORKFLOW | PROVIDER) [ARGS ...]\n")
        workflows_yaml = _load_workflows()
        workflows = (workflows_yaml or {}).get("workflows") or []
        workflow_names = [w["name"] for w in workflows if w.get("name")]
        providers_names = providers.get_provider_names()
        print(f'Positional arguments:\n'
              f'  WORKFLOW      {{{",".join(workflow_names)}}}\n'
              f'  PROVIDER      {{{",".join(providers_names)}}}\n')
        print("Options:\n"
              "  -d, --detach   Do not poll for status update and logs\n"
              "  -h, --help     Show this help output, or the help for a specified workflow or provider.\n")
        print("To see the help output for a particular workflow or provider, use the following command:\n"
              "  dstack run (WORKFLOW | PROVIDER) --help")
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
            run_name = backend.create_run(repo_data.repo_user_name, repo_data.repo_name)
            jobs = provider.submit_jobs(run_name)
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
    parser.add_argument("workflow_or_provider", metavar="TARGET", type=str,
                        help="A name of a workflow or a provider", nargs="?")
    parser.add_argument("-d", "--detach", help="Do not poll for status update and logs", action="store_true")
    parser.add_argument("args", metavar="ARGS", nargs=argparse.ZERO_OR_MORE, help="Override provider arguments")
    parser.add_argument('-h', '--help', action='store_true', default=argparse.SUPPRESS,
                        help='Show this help message and exit')

    parser.set_defaults(func=run_workflow_func)
