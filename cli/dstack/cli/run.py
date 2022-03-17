import json
import os
import sys
from argparse import Namespace

import requests
import yaml
from git import InvalidGitRepositoryError
from jsonschema import validate, ValidationError

from dstack.cli.logs import logs_func
from dstack.cli.schema import workflows_schema_yaml
from dstack.cli.common import load_workflows, load_variables, load_repo_data
from dstack.cli.status import status_func
from dstack.config import get_config, ConfigurationError


def register_parsers(main_subparsers, main_parser):
    parser = main_subparsers.add_parser("run", help="Run a workflow")
    workflows_yaml = load_workflows()
    variables = load_variables()
    workflows = (workflows_yaml.get("workflows") or []) if workflows_yaml is not None else []
    workflow_names = [w.get("name") for w in workflows]
    subparsers = parser.add_subparsers()
    for workflow_name in workflow_names:
        workflow_parser = subparsers.add_parser(workflow_name, help=f"Run the '{workflow_name}' workflow")
        workflow_parser.add_argument("--follow", "-f",
                                     help="Whether to continuously poll and print logs of the workflow. "
                                          "By default, the command doesn't print logs. To exit from this "
                                          "mode, use Control-C.", action="store_true")

        # TODO: Walk the graph of dependencies and only include the variables from dependencies
        # Because our workflow may depend on other workflows, we allow overriding all variables
        workflow_variables = {}
        for section in variables:
            v_variables = variables.get(section)
            for name in v_variables:
                workflow_variables[name] = v_variables[name]
                workflow_parser.add_argument("--" + name,
                                             help=f"by default, the value is {pretty_print_variable_value(v_variables[name])}",
                                             type=str,
                                             nargs="?")

        def run_workflow(_workflow_name):
            def _run_workflow(args):
                if len(workflows) > 0:
                    try:
                        validate(workflows_yaml, yaml.load(workflows_schema_yaml, Loader=yaml.FullLoader))
                        repo_url, repo_branch, repo_hash, repo_diff = load_repo_data()
                        dstack_config = get_config()
                        # TODO: Support non-default profiles
                        profile = dstack_config.get_profile("default")

                        # TODO: Support large repo_diff
                        headers = {
                            "Content-Type": f"application/json; charset=utf-8"
                        }
                        if profile.token is not None:
                            headers["Authorization"] = f"Bearer {profile.token}"

                        def fix_variable_name(name: str):
                            alternative_name = name.replace("_", "-")
                            if alternative_name in workflow_variables and name not in workflow_variables:
                                return alternative_name
                            else:
                                return name

                        _variables = {fix_variable_name(k): v for (k, v) in vars(args).items() if
                                      k != "func" and k != "follow" and v is not None}
                        data = {
                            "workflow_name": _workflow_name,
                            "repo_url": repo_url,
                            "repo_branch": repo_branch,
                            "repo_hash": repo_hash,
                            "variables": _variables
                        }
                        if repo_diff:
                            data["repo_diff"] = repo_diff
                        data_bytes = json.dumps(data).encode("utf-8")
                        response = requests.request(method="POST", url=f"{profile.server}/runs/submit",
                                                    data=data_bytes,
                                                    headers=headers, verify=profile.verify)
                        if response.status_code == 200:
                            status_func(Namespace(run_name=response.json().get("run_name"), n=1, no_jobs=False))
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
                else:
                    sys.exit(f"No workflows defined in {os.getcwd()}/.dstack/workflows.yaml")

            return _run_workflow

        workflow_parser.set_defaults(func=run_workflow(workflow_name))

    def default_run_workflow(_: Namespace):
        parser.print_help()
        exit(1)

    parser.set_defaults(func=default_run_workflow)


def pretty_print_variable_value(obj):
    if type(obj) is str:
        return f"\"{obj}\""
    else:
        return str(obj)
