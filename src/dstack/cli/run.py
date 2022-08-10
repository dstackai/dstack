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
from dstack.backend import load_backend, Backend
from dstack.cli.logs import logs_func
from dstack.cli.runs import runs_func
from dstack.cli.schema import workflows_schema_yaml
from dstack.config import ConfigError
from dstack.jobs import JobStatus
from dstack.repo import load_repo


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
        if args.workflow_or_provider not in providers.get_providers_names():
            sys.exit(f"No workflow or provider `{args.workflow_or_provider}` is found")

        provider_name = args.workflow_or_provider

    return provider_name, provider_args, workflow_name, workflow_data


# TODO: Stop the run on SIGTERM, SIGHUP, etc
def poll_run(repo_user_name: str, repo_name: str, run_name: str, backend: Backend):
    console = Console()
    try:
        console.print()
        availability_issues_printed = False
        with Progress(TextColumn("[progress.description]{task.description}"), SpinnerColumn(),
                      transient=True, ) as progress:
            task = progress.add_task("Provisioning... It may take up to a minute.", total=None)
            while True:
                run = backend.get_runs(repo_user_name, repo_name, run_name)[0]
                if run.status not in [JobStatus.SUBMITTED]:
                    progress.update(task, total=100)
                    break
                availability_issues = run.availability_issues
                if availability_issues:
                    if not availability_issues_printed:
                        issue = availability_issues[0]
                        progress.update(task, description=f"[yellow]⛔️ {issue.message}")
                        availability_issues_printed = True
                elif availability_issues_printed:
                    progress.update(task, description="Provisioning... It may take up to a minute.")
                    availability_issues_printed = False
                time.sleep(3)
        console.print("Provisioning... It may take up to a minute. [green]✓[/]")
        console.print()
        console.print("[grey58]To interrupt, press Ctrl+C.[/]")
        console.print()
        logs_func(Namespace(run_name=run_name, follow=True, since="1d", from_run=True))
    except KeyboardInterrupt:
        if Confirm.ask(f" [red]Stop the run `{run_name}`?[/]"):
            backend.stop_jobs(repo_user_name, repo_name, run_name, abort=True)
            console.print(f"[grey58]OK[/]")


def run_workflow_func(args: Namespace):
    if not args.workflow_or_provider:
        print("Usage: dstack run [-d] [-h] WORKFLOW | PROVIDER [ARGS ...]\n")
        workflows_yaml = _load_workflows()
        workflows = (workflows_yaml or {}).get("workflows") or []
        if workflows:
            print("Workflows:")
            for w in workflows:
                if w.get("name"):
                    print(f"  {w['name']}")
        else:
            print("No workflows found in .dstack/workflows.yaml.")
        print()
        print("Providers:")
        for p in providers.get_providers_names():
            print(f"  {p}")
        print("\n"
              "Options:\n"
              "  -d, --detach   Do not poll for status update and logs"
              "  -h, --help     Show this help output, or the help for a specified workflow or provider.")
    else:
        try:
            repo = load_repo()
            backend = load_backend()

            provider_name, provider_args, workflow_name, workflow_data = parse_run_args(args)

            provider = providers.load_provider(provider_name)

            if hasattr(args, "help") and args.help:
                provider.help(workflow_name)
                sys.exit()

            provider.load(provider_args, workflow_name, workflow_data)
            run_name = backend.create_run(repo.repo_user_name, repo.repo_name)
            provider.submit_jobs(run_name)
            runs_func(Namespace(run_name=run_name, all=False))
            if not args.detach:
                poll_run(repo.repo_user_name, repo.repo_name, run_name, backend)

        except ConfigError:
            sys.exit(f"Call 'dstack config' first")
        except InvalidGitRepositoryError:
            sys.exit(f"{os.getcwd()} is not a Git repo")
        except ValidationError as e:
            sys.exit(f"There a syntax error in {os.getcwd()}/.dstack/workflows.yaml:\n\n{e}")


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("run", help="Run a workflow", add_help=False)
    parser.add_argument("workflow_or_provider", metavar="WORKFLOW | PROVIDER", type=str,
                        help="A name of a workflow or a provider", nargs="?")
    parser.add_argument("-d", "--detach", help="Do not poll for status update and logs", action="store_true")
    parser.add_argument("args", metavar="ARGS", nargs=argparse.ZERO_OR_MORE, help="Override provider arguments")
    parser.add_argument('-h', '--help', action='store_true', default=argparse.SUPPRESS,
                        help='Show this help message and exit')

    parser.set_defaults(func=run_workflow_func)
