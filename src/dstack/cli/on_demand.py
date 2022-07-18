import sys
from argparse import Namespace

from rich import print

from rich.prompt import Confirm
from dstack.cli.common import do_post
from dstack.config import ConfigurationError


def enable_func(_: Namespace):
    try:
        data = {
            "enabled": True
        }
        response = do_post("on-demand/settings/update", data)
        if response.status_code == 200:
            print(f"[grey58]OK[/]")
        else:
            response.raise_for_status()
    except ConfigurationError:
        sys.exit(f"Call 'dstack config' first")


def disable_func(args: Namespace):
    if args.force or Confirm.ask("Are you sure you want to disable on-demand runners?"):
        try:
            data = {
                "enabled": False
            }
            response = do_post("on-demand/settings/update", data)
            if response.status_code == 200:
                print(f"[grey58]OK[/]")
            else:
                response.raise_for_status()
        except ConfigurationError:
            sys.exit(f"Call 'dstack config' first")
    else:
        print(f"[red]Cancelled[/]")


def status_func(_: Namespace):
    try:
        response = do_post("on-demand/settings")
        if response.status_code == 200:
            response_json = response.json()
            print(f"[magenta]Enabled[/]: " + (
                f"[red]No[/]" if response_json.get(
                    "enabled") is False else f"[green]Yes[/]"))
        else:
            response.raise_for_status()
    except ConfigurationError:
        sys.exit(f"Call 'dstack config' first")


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("on-demand", help="Manage on-demand settings")

    subparsers = parser.add_subparsers()

    status_parser = subparsers.add_parser("status", help="Show if on-demand runners is enabled")
    status_parser.set_defaults(func=status_func)

    disable_parser = subparsers.add_parser("disable", help="Disable on-demand runners")
    disable_parser.add_argument("--force", "-f", help="Don't ask for confirmation", action="store_true")
    disable_parser.set_defaults(func=disable_func)

    enable_parser = subparsers.add_parser("enable", help="Enable on-demand runners")
    enable_parser.set_defaults(func=enable_func)
