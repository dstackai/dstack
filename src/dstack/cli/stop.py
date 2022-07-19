import json
import sys
from argparse import Namespace

from rich import print
import requests
from rich.prompt import Confirm

from dstack.config import get_config, ConfigurationError


def default_stop_workflow(args: Namespace):
    if (args.run_name and (args.yes or Confirm.ask(f"[red]Stop {args.run_name}?[/]"))) \
            or (args.all and (args.yes or Confirm.ask("[red]Stop all runs?[/]"))):
        try:
            dstack_config = get_config()
            # TODO: Support non-default profiles
            profile = dstack_config.get_profile("default")
            headers = {
                "Content-Type": f"application/json; charset=utf-8"
            }
            if profile.token is not None:
                headers["Authorization"] = f"Bearer {profile.token}"

            data = {"run_name": args.run_name,
                    "abort": args.abort is True}
            if args.workflow_name:
                data["workflow_name"] = args.workflow_name
            else:
                data["all"] = True
            response = requests.request(method="POST", url=f"{profile.server}/runs/workflows/stop",
                                        data=json.dumps(data).encode("utf-8"),
                                        headers=headers, verify=profile.verify)
            if response.status_code != 200:
                response.raise_for_status()
            print(f"[grey58]OK[/]")
        except ConfigurationError:
            sys.exit(f"Call 'dstack config' first")
    else:
        if not args.run_name and not args.all:
            sys.exit("Specify a run name or use --all to stop all workflows")


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("stop", help="Stop runs")

    parser.add_argument("run_name", metavar="RUN", type=str, nargs="?", help="A name of a run")
    parser.add_argument("workflow_name", metavar="WORKFLOW", type=str, nargs="?", help="A name of a workflow")
    parser.add_argument("-a", "--all", help="All runs", dest="all", action="store_true")
    parser.add_argument("--abort", help="Don't wait for a graceful stop", dest="abort", action="store_true")
    parser.add_argument("--yes", "-y", help="Don't ask for confirmation", action="store_true")

    parser.set_defaults(func=default_stop_workflow)
