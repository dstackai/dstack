import argparse
import os
import sys
import tempfile
import time
from argparse import Namespace
from typing import List, Optional

import yaml
from git import InvalidGitRepositoryError
from jsonschema import validate, ValidationError
from rich.console import Console
from rich.progress import SpinnerColumn, Progress, TextColumn
from rich.prompt import Confirm

from dstack.backend import get_backend, Backend
from dstack.cli.common import load_workflows, load_variables, load_repo_data, load_providers
from dstack.cli.logs import logs_func
from dstack.cli.runs import runs_func
from dstack.cli.schema import workflows_schema_yaml
from dstack.config import ConfigError
from dstack.providers import Provider

SLEEP_SECONDS = 3

built_in_provider_names = ["bash", "python", "tensorboard", "torchrun",
                           "docker",
                           "curl",
                           "lab", "notebook",
                           "code", "streamlit", "gradio", "fastapi"]


def init_built_in_provider(provider_name: str):
    provider_module = None
    if provider_name == "bash":
        import dstack.providers.bash.main as m
        provider_module = m
    if provider_name == "python":
        import dstack.providers.python.main as m
        provider_module = m
    if provider_name == "tensorboard":
        import dstack.providers.tensorboard.main as m
        provider_module = m
    if provider_name == "curl":
        import dstack.providers.curl.main as m
        provider_module = m
    if provider_name == "docker":
        import dstack.providers.docker.main as m
        provider_module = m
    if provider_name == "torchrun":
        import dstack.providers.torchrun.main as m
        provider_module = m
    if provider_name == "lab":
        import dstack.providers.lab.main as m
        provider_module = m
    if provider_name == "notebook":
        import dstack.providers.notebook.main as m
        provider_module = m
    if provider_name == "code":
        import dstack.providers.code.main as m
        provider_module = m
    if provider_name == "streamlit":
        import dstack.providers.streamlit.main as m
        provider_module = m
    if provider_name == "gradio":
        import dstack.providers.gradio.main as m
        provider_module = m
    if provider_name == "fastapi":
        import dstack.providers.fastapi.main as m
        provider_module = m
    return provider_module.__provider__() if provider_module else None


def load_built_in_provider(provider: Provider, provider_args: List[str], workflow_name: str, workflow_data: dict,
                           repo_user_name, repo_name, repo_branch, repo_hash, repo_diff):
    job_ids_csv_file, job_ids_csv_filename = tempfile.mkstemp()
    workflow_yaml_file, workflow_yaml_filename = tempfile.mkstemp()
    os.environ["REPO_PATH"] = os.getcwd()
    os.environ["JOB_IDS_CSV"] = job_ids_csv_filename
    with os.fdopen(workflow_yaml_file, 'w') as tmp:
        workflow_yaml = {
            "run_name": None,
            "provider_args": provider_args,
            "workflow_name": workflow_name,
            "provider_name": provider.provider_name,
            "repo_user_name": repo_user_name,
            "repo_name": repo_name,
            "repo_branch": repo_branch,
            "repo_hash": repo_hash,
            "repo_diff": repo_diff,
            "variables": [],
            "previous_job_ids": [],
        }
        if workflow_name and workflow_data:
            del workflow_data["name"]
            del workflow_data["provider"]
            if workflow_data.get("help"):
                del workflow_data["help"]
            if workflow_data.get("depends-on"):
                del workflow_data["depends-on"]
            workflow_yaml.update(workflow_data)
        # TODO: Handle previous_job_ids
        # TODO: Handle variables
        yaml.dump(workflow_yaml, tmp)
    os.environ["WORKFLOW_YAML"] = workflow_yaml_filename
    provider.load()
    # TODO: Cleanup tmp files after provider.run


def parse_run_args(args):
    provider_args = args.vars + args.args + args.unknown
    workflow_name = None
    workflow_data = None
    provider_name = None
    provider = None
    provider_repo = None
    provider_branch = None
    variables = {}

    workflows_yaml = load_workflows()
    workflows = (workflows_yaml.get("workflows") or []) if workflows_yaml is not None else []
    if workflows:
        validate(workflows_yaml, yaml.load(workflows_schema_yaml, Loader=yaml.FullLoader))
    workflow_names = [w.get("name") for w in workflows]
    workflow_providers = {w.get("name"): w.get("provider") for w in workflows}

    workflow_variables = load_variables()

    providers_yaml = load_providers()
    providers = (providers_yaml.get("providers") or []) if providers_yaml is not None else []
    provider_names = [p.get("name") for p in providers]

    if args.workflow_or_provider in workflow_names:
        workflow_name = args.workflow_or_provider
        workflow_data = next(w for w in workflows if w.get("name") == workflow_name)
        if isinstance(workflow_providers[workflow_name], str):
            provider_name = workflow_providers[workflow_name]
        else:
            provider_name = workflow_providers[workflow_name]["name"]
            provider_repo = workflow_providers[workflow_name]["repo"]
        if "@" in provider_name:
            tokens = provider_name.split('@', maxsplit=1)
            provider_name = tokens[0]
            provider_branch = tokens[1]

        for idx, arg in enumerate(provider_args[:]):
            if arg.startswith('--'):
                arg_name = arg[2:]
                if workflow_variables.get(workflow_name) and arg_name in workflow_variables[workflow_name] \
                        and idx < len(provider_args) - 1:
                    variables[arg_name] = provider_args[idx + 1]
                    del provider_args[idx]
                    del provider_args[idx]
                if workflow_variables.get("global") and arg_name in workflow_variables["global"] \
                        and idx < len(provider_args) - 1:
                    variables[arg_name] = provider_args[idx + 1]
                    del provider_args[idx]
                    del provider_args[idx]
    else:
        if "@" in args.workflow_or_provider:
            tokens = args.workflow_or_provider.split('@', maxsplit=1)
            provider_name = tokens[0]
            provider_branch = tokens[1]
        else:
            provider_name = args.workflow_or_provider

        # TODO: Support --repo to enable providers from other repos
        if not provider_branch:
            if provider_name not in (provider_names + built_in_provider_names):
                sys.exit(f"No workflow or provider with the name `{provider_name}` is found.\n"
                         f"If you're referring to a workflow, make sure it is defined in .dstack/workflows.yaml.\n"
                         f"If you're referring to a provider, make sure it is defined in .dstack/providers.yaml.")

        if workflow_variables.get("global"):
            for idx, arg in enumerate(provider_args[:]):
                if arg.startswith('--'):
                    arg_name = arg[2:]
                    if arg_name in workflow_variables["global"] \
                            and idx < len(provider_args) - 1:
                        variables[arg_name] = provider_args[idx + 1]
                        del provider_args[idx]
                        del provider_args[idx]

    is_built_in_provider = provider_name in built_in_provider_names and not provider_branch
    built_in_provider = init_built_in_provider(provider_name) if is_built_in_provider else None
    # TODO: Support depends-on
    instant_run = is_built_in_provider and (not workflow_data or not workflow_data.get("depends-on"))

    return provider_args, provider_branch, provider_name, provider_repo, variables, \
           workflow_data, workflow_name, built_in_provider, instant_run


def stop_run(run_name: str, console: Console):
    console.log("[TODO] Stopping a run...")


# TODO: Stop the run on SIGTERM, SIGHUP, etc
def poll_run(run_name: str, workflow_name: Optional[str], backend: Backend):
    console = Console()
    try:
        console.print()
        availability_issues_printed = False
        with Progress(TextColumn("[progress.description]{task.description}"), SpinnerColumn(),
                      transient=True, ) as progress:
            task = progress.add_task("Provisioning... It may take up to a minute.", total=None)
            while True:
                progress.log("[TODO] Polling run status...")
                run = {"status": "running"}  # get_runs(run_name, workflow_name, profile)[0]
                if run["status"] not in ["submitted", "queued"]:
                    progress.update(task, total=100)
                    break
                availability_issues = run.get("availability_issues")
                if availability_issues:
                    if not availability_issues_printed:
                        issue = availability_issues[0]
                        progress.update(task, description=f"[yellow]⛔️ {issue['message']}")
                        availability_issues_printed = True
                elif availability_issues_printed:
                    progress.update(task, description="Provisioning... It may take up to a minute.")
                    availability_issues_printed = False
                time.sleep(SLEEP_SECONDS)
        console.print("Provisioning... It may take up to a minute. [green]✓[/]")
        console.print()
        console.print("[grey58]To interrupt, press Ctrl+C.[/]")
        console.print()
        logs_func(Namespace(run_name=run_name, workflow_name=workflow_name, follow=True, since="1d", from_run=True))
    except KeyboardInterrupt:
        if Confirm.ask(f" [red]Stop {run_name}?[/]"):
            stop_run(run_name, console)


def run_workflow_func(args):
    if not args.workflow_or_provider:
        print("Usage: dstack run [-d] [-h] (WORKFLOW | PROVIDER) [ARGS ...]\n")
        workflows_yaml = load_workflows()
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
        for p in built_in_provider_names:
            print(f"  {p}")
        print("\n"
              "Options:\n"
              "  -d, --detach   Do not poll for status update and logs"
              "  -h, --help     Show this help output, or the help for a specified workflow or provider.")
    else:
        try:
            repo_user_name, repo_name, repo_branch, repo_hash, repo_diff = load_repo_data()
            backend = get_backend()

            provider_args, provider_branch, provider_name, \
                provider_repo, variables, workflow_data, \
                workflow_name, built_in_provider, instant_run = parse_run_args(args)

            if hasattr(args, "help") and args.help and built_in_provider:
                built_in_provider.help(workflow_name)
                sys.exit()

            if instant_run:
                load_built_in_provider(built_in_provider, provider_args, workflow_name, workflow_data,
                                       repo_user_name, repo_name, repo_branch, repo_hash, repo_diff)

            run_name = backend.next_run_name()
            if instant_run:
                built_in_provider.run(run_name)
            runs_func(Namespace(run_name=run_name, all=False))
            if not args.detach:
                poll_run(run_name, workflow_name, backend)

        except ConfigError:
            sys.exit(f"Call 'dstack config' first")
        except InvalidGitRepositoryError:
            sys.exit(f"{os.getcwd()} is not a Git repo")
        except ValidationError as e:
            sys.exit(f"There a syntax error in {os.getcwd()}/.dstack/workflows.yaml:\n\n{e}")


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("run", help="Run a workflow", add_help=False)
    parser.add_argument("workflow_or_provider", metavar="(WORKFLOW | PROVIDER)", type=str,
                        help="A name of a workflow or a provider", nargs="?")
    parser.add_argument("-d", "--detach", help="Do not poll for status update and logs", action="store_true")
    parser.add_argument("vars", metavar="VARS", nargs=argparse.ZERO_OR_MORE,
                        help="Override workflow variables")
    parser.add_argument("args", metavar="ARGS", nargs=argparse.ZERO_OR_MORE, help="Override provider arguments")
    parser.add_argument('-h', '--help', action='store_true', default=argparse.SUPPRESS,
                        help='Show this help message and exit')

    parser.set_defaults(func=run_workflow_func)
