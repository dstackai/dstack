import argparse
import json
import os
import sys
from argparse import Namespace

import pkg_resources
import requests
import yaml
from git import InvalidGitRepositoryError
from jsonschema import validate, ValidationError

from dstack.cli.logs import logs_func
from dstack.cli.schema import workflows_schema_yaml
from dstack.cli.common import load_workflows, load_variables, load_repo_data, load_providers
from dstack.cli.runs import runs_func
from dstack.config import get_config, ConfigurationError


def load_built_in_providers():
    resource_package = __name__
    resource_path = '/'.join(['providers.yaml'])
    providers_stream = pkg_resources.resource_string(resource_package, resource_path)
    return yaml.load(providers_stream, Loader=yaml.FullLoader)


# TODO: Support dstack run (WORKFLOW | PROVIDER[:BRANCH]) --dry-run (dry-run is a boolean property of a run,
#  the dry-run arguments automatically enables --follow)
# TODO: Support dstack run (WORKFLOW | PROVIDER[:BRANCH]) --help
def register_parsers(main_subparsers, main_parser):
    parser = main_subparsers.add_parser("run", help="Run a workflow or provider"
                                        )
    parser.add_argument("workflow_or_provider", metavar="(WORKFLOW | PROVIDER[:BRANCH])", type=str,
                        help="A name of a workflow or a provider")
    parser.add_argument("--follow", "-f", help="Whether to continuously poll for new logs. By default, the command "
                                               "will exit once there are no more logs to display. To exit from this "
                                               "mode, use Control-C.", action="store_true")
    parser.add_argument("vars", metavar="VARS", nargs=argparse.ZERO_OR_MORE,
                        help="Override workflow workflow_variables")
    parser.add_argument("args", metavar="ARGS", nargs=argparse.ZERO_OR_MORE, help="Override provider arguments")
    workflows_yaml = load_workflows()
    providers_yaml = load_providers()
    built_in_providers_yaml = load_built_in_providers()
    workflow_variables = load_variables()
    workflows = (workflows_yaml.get("workflows") or []) if workflows_yaml is not None else []
    providers = (providers_yaml.get("providers") or []) if providers_yaml is not None else []
    built_in_providers = (built_in_providers_yaml.get("providers") or []) if built_in_providers_yaml is not None else []
    workflow_names = [w.get("name") for w in workflows]
    provider_names = [p.get("name") for p in providers]
    built_in_provider_names = [p.get("name") for p in built_in_providers]
    workflow_providers = {w.get("name"): w.get("provider") for w in workflows}

    def default_run_func(args):
        try:
            if workflows:
                validate(workflows_yaml, yaml.load(workflows_schema_yaml, Loader=yaml.FullLoader))
            repo_url, repo_branch, repo_hash, repo_diff = load_repo_data()
            dstack_config = get_config()
            # # TODO: Support non-default profiles
            profile = dstack_config.get_profile("default")

            provider_args = args.vars + args.args + args.unknown

            workflow_name = None
            provider_name = None
            provider_repo = None
            provider_branch = None
            variables = {}
            if args.workflow_or_provider in workflow_names:
                workflow_name = args.workflow_or_provider
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

            # # TODO: Support large repo_diff
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

            data_bytes = json.dumps(data).encode("utf-8")
            response = requests.request(method="POST", url=f"{profile.server}/runs/submit",
                                        data=data_bytes,
                                        headers=headers, verify=profile.verify)
            if response.status_code == 200:
                runs_func(Namespace(run_name=response.json().get("run_name"), last=1))
                if args.follow:
                    logs_func(Namespace(run_name_or_job_id=response.json().get("run_name"),
                                        follow=True, since="1d"))
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
