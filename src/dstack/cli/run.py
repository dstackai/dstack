import argparse
import json
import os
import sys
import tempfile
from argparse import Namespace
from typing import List

import requests
import yaml
from git import InvalidGitRepositoryError
from jsonschema import validate, ValidationError

from dstack import Provider
from dstack.cli.common import load_workflows, load_variables, load_repo_data, load_providers, get_user_info
from dstack.cli.logs import logs_func
from dstack.cli.runs import runs_func
from dstack.cli.schema import workflows_schema_yaml
from dstack.config import get_config, ConfigurationError, Profile
from dstack.server import __server_url__

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
                           profile: Profile, repo_url, repo_branch, repo_hash, repo_diff):
    job_ids_csv_file, job_ids_csv_filename = tempfile.mkstemp()
    workflow_yaml_file, workflow_yaml_filename = tempfile.mkstemp()
    os.environ["DSTACK_SERVER"] = __server_url__
    os.environ["DSTACK_TOKEN"] = profile.token
    user_info = get_user_info(profile)
    os.environ["DSTACK_USER"] = user_info["user_name"]
    os.environ["DSTACK_AWS_ACCESS_KEY_ID"] = user_info["default_configuration"]["aws_access_key_id"]
    os.environ["DSTACK_AWS_SECRET_ACCESS_KEY"] = user_info["default_configuration"]["aws_secret_access_key"]
    os.environ["DSTACK_AWS_DEFAULT_REGION"] = user_info["default_configuration"]["aws_region"]
    os.environ["DSTACK_ARTIFACTS_S3_BUCKET"] = user_info["default_configuration"]["artifacts_s3_bucket"]
    os.environ["REPO_PATH"] = os.getcwd()
    os.environ["JOB_IDS_CSV"] = job_ids_csv_filename
    with os.fdopen(workflow_yaml_file, 'w') as tmp:
        workflow_yaml = {
            "user_name": user_info['user_name'],
            "run_name": None,
            "provider_args": provider_args,
            "workflow_name": workflow_name,
            "repo_url": repo_url,
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


def submit_run(workflow_name, provider_name, provider_branch, provider_repo, provider_args, repo_url, repo_branch,
               repo_hash, repo_diff, variables, instant_run, profile):
    headers = {
        "Content-Type": f"application/json; charset=utf-8"
    }
    if profile.token is not None:
        headers["Authorization"] = f"Bearer {profile.token}"
    data = {
        "workflow_name": workflow_name,
        "provider_name": provider_name,
        "provider_repo": provider_repo,
        "provider_branch": provider_branch,
        "provider_args": provider_args,
        "repo_url": repo_url,
        "repo_branch": repo_branch,
        "repo_hash": repo_hash,
        "variables": variables
    }
    if repo_diff:
        data["repo_diff"] = repo_diff
    if instant_run:
        data["status"] = "running"
    data_bytes = json.dumps(data).encode("utf-8")
    response = requests.request(method="POST", url=f"{profile.server}/runs/submit",
                                data=data_bytes,
                                headers=headers, verify=profile.verify)
    return response


def update_run(run_name: str, status: str, profile: Profile):
    headers = {
        "Content-Type": f"application/json; charset=utf-8"
    }
    if profile.token is not None:
        headers["Authorization"] = f"Bearer {profile.token}"
    data = {
        "run_name": run_name,
        "status": status,
    }
    data_bytes = json.dumps(data).encode("utf-8")
    response = requests.request(method="POST", url=f"{profile.server}/runs/update",
                                data=data_bytes,
                                headers=headers, verify=profile.verify)
    if response.status_code != 200:
        response.raise_for_status()


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


# TODO: Support --dry-run
def register_parsers(main_subparsers, main_parser):
    parser = main_subparsers.add_parser("run", help="Run a workflow", add_help=False)
    parser.add_argument("workflow_or_provider", metavar="(WORKFLOW | PROVIDER[@BRANCH])", type=str,
                        help="A name of a workflow or a provider")
    parser.add_argument("--follow", "-f", help="Whether to continuously poll for new logs. By default, the command "
                                               "will exit once there are no more logs to display. To exit from this "
                                               "mode, use Control-C.", action="store_true")
    parser.add_argument("vars", metavar="VARS", nargs=argparse.ZERO_OR_MORE,
                        help="Override workflow variables")
    parser.add_argument("args", metavar="ARGS", nargs=argparse.ZERO_OR_MORE, help="Override provider arguments")
    parser.add_argument('-h', '--help', action='store_true', default=argparse.SUPPRESS,
                        help='Show this help message and exit')

    def default_run_func(args):
        try:
            repo_url, repo_branch, repo_hash, repo_diff = load_repo_data()
            profile = get_config().get_profile("default")

            provider_args, provider_branch, provider_name, \
            provider_repo, variables, workflow_data, \
            workflow_name, built_in_provider, instant_run = parse_run_args(args)

            if hasattr(args, "help") and args.help and built_in_provider:
                built_in_provider.help(workflow_name)
                sys.exit()

            if instant_run:
                load_built_in_provider(built_in_provider, provider_args, workflow_name, workflow_data,
                                       profile, repo_url, repo_branch, repo_hash, repo_diff)

            response = submit_run(workflow_name, provider_name, provider_branch, provider_repo, provider_args, repo_url,
                                  repo_branch, repo_hash, repo_diff, variables, instant_run, profile)
            if response.status_code == 200:
                run_name = response.json().get("run_name")
                if instant_run:
                    built_in_provider.run(run_name)
                runs_func(Namespace(run_name=run_name, all=False))
                if args.follow:
                    logs_func(Namespace(run_name=run_name, follow=True, since="1d"))
            elif response.status_code == 404 and response.json().get("message") == "repo not found":
                sys.exit("Call 'dstack init' first")
            else:
                response.raise_for_status()

        except ConfigurationError:
            sys.exit(f"Call 'dstack config' first")
        except InvalidGitRepositoryError:
            sys.exit(f"{os.getcwd()} is not a Git repo")
        except ValidationError as e:
            sys.exit(f"There a syntax error in {os.getcwd()}/.dstack/workflows.yaml:\n\n{e}")

    parser.set_defaults(func=default_run_func)
