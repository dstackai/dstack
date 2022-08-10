import os
import sys
import webbrowser
from argparse import Namespace

from git import InvalidGitRepositoryError
from rich import print


def apps_func(args: Namespace):
    try:
        dstack_config = get_config()
        profile = dstack_config.get_profile("default")
        workflows = get_runs(args.run_name, args.workflow_name, profile=profile)

        apps = []
        for workflow in filter(lambda w: not args.workflow_name or w.workflow_name == args.workflow_name, workflows):
            for app in workflow.get("apps") or []:
                apps.append(app)
        if len(apps) > 0:
            url = apps[0].get("url")
            if url:
                print(f"The application url is {url}")
                print("Opening it in the browser...")
                webbrowser.open(apps[0]["url"])
                print(f"[grey58]OK[/]")
            else:
                sys.exit("Application is not initialized yet")
        else:
            sys.exit("No application is found")
    except InvalidGitRepositoryError:
        sys.exit(f"{os.getcwd()} is not a Git repo")
    except ConfigurationError:
        sys.exit(f"Call 'dstack config' first")


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("app", help="Open an app")

    parser.add_argument("run_name", metavar="RUN", type=str, help="A name of a run")
    parser.set_defaults(func=apps_func)
