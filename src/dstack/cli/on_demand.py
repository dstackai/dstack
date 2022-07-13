import sys
from argparse import Namespace

import colorama
from tabulate import tabulate

from dstack.cli import confirm
from dstack.cli.common import do_post, do_get, __pretty_print_gpu_resources, pretty_date
from dstack.config import ConfigurationError


def enable_func(_: Namespace):
    try:
        data = {
            "enabled": True
        }
        response = do_post("on-demand/settings/update", data)
        if response.status_code == 200:
            print(f"{colorama.Fore.LIGHTBLACK_EX}OK{colorama.Fore.RESET}")
        else:
            response.raise_for_status()
    except ConfigurationError:
        sys.exit(f"Call 'dstack config' first")


def disable_func(args: Namespace):
    if args.force or confirm(f"Are you sure you want to disable on-demand runners?"):
        try:
            data = {
                "enabled": False
            }
            response = do_post("on-demand/settings/update", data)
            if response.status_code == 200:
                print(f"{colorama.Fore.LIGHTBLACK_EX}OK{colorama.Fore.RESET}")
            else:
                response.raise_for_status()
        except ConfigurationError:
            sys.exit(f"Call 'dstack config' first")
    else:
        print(f"{colorama.Fore.RED}Cancelled{colorama.Fore.RESET}")


def limit_func(args: Namespace):
    if args.delete:
        if args.force or confirm(f"Are you sure you want to delete the limit?"):
            try:
                data = {
                    "region_name": args.region,
                    "instance_type": args.instance_type,
                    "purchase_type": "spot" if args.spot else "on-demand"
                }
                response = do_post("on-demand/limits/delete", data)
                if response.status_code == 200:
                    print(f"{colorama.Fore.LIGHTBLACK_EX}OK{colorama.Fore.RESET}")
                if response.status_code == 400 and response.json().get("message") == "aws is not configured":
                    sys.exit(f"Call 'dstack aws config' first")
                if response.status_code == 404 and response.json().get("message") == "limit not found":
                    sys.exit(f"Limit doesn't exist")
                if response.status_code == 404 and response.json().get("message") == "region not found":
                    sys.exit(f"Region is not supported")
                if response.status_code == 404 and response.json().get("message") == "instance type not found":
                    sys.exit(f"Instance type is not supported")
                else:
                    response.raise_for_status()
            except ConfigurationError:
                sys.exit(f"Call 'dstack config' first")
        else:
            print(f"{colorama.Fore.RED}Cancelled{colorama.Fore.RESET}")
    else:
        try:
            data = {
                "region_name": args.region,
                "instance_type": args.instance_type,
                "purchase_type": "spot" if args.spot else "on-demand",
                "maximum": args.max,
            }
            response = do_post("on-demand/limits/set", data)
            if response.status_code == 200:
                print(f"{colorama.Fore.LIGHTBLACK_EX}OK{colorama.Fore.RESET}")
            if response.status_code == 400 and response.json().get("message") == "aws is not configured":
                sys.exit(f"Call 'dstack aws config' first")
            if response.status_code == 404 and response.json().get("message") == "region not found":
                sys.exit(f"Region is not supported")
            if response.status_code == 404 and response.json().get("message") == "instance type not found":
                sys.exit(f"Instance type is not supported")
            else:
                response.raise_for_status()
        except ConfigurationError:
            sys.exit(f"Call 'dstack config' first")


def status_func(_: Namespace):
    try:
        response = do_post("on-demand/settings")
        if response.status_code == 200:
            response_json = response.json()
            print(f"{colorama.Fore.LIGHTMAGENTA_EX}Enabled{colorama.Fore.RESET}: " + (
                f"{colorama.Fore.LIGHTRED_EX}No{colorama.Fore.RESET}" if response_json.get(
                    "enabled") is False else f"{colorama.Fore.LIGHTGREEN_EX}Yes{colorama.Fore.RESET}"))
        else:
            response.raise_for_status()
    except ConfigurationError:
        sys.exit(f"Call 'dstack config' first")


def limits_func(args: Namespace):
    if args.delete_all:
        if args.force or confirm(f"Are you sure you want to delete all limits?"):
            try:
                response = do_post("on-demand/limits/clear")
                if response.status_code == 200:
                    print(f"{colorama.Fore.LIGHTBLACK_EX}OK{colorama.Fore.RESET}")
                else:
                    response.raise_for_status()
            except ConfigurationError:
                sys.exit(f"Call 'dstack config' first")
        else:
            print(f"{colorama.Fore.RED}Cancelled{colorama.Fore.RESET}")
    else:
        try:
            response = do_get("on-demand/limits/query")
            if response.status_code == 200:
                table_headers = [
                    f"{colorama.Fore.LIGHTMAGENTA_EX}REGION{colorama.Fore.RESET}",
                    f"{colorama.Fore.LIGHTMAGENTA_EX}INSTANCE TYPE{colorama.Fore.RESET}",
                    f"{colorama.Fore.LIGHTMAGENTA_EX}CPU{colorama.Fore.RESET}",
                    f"{colorama.Fore.LIGHTMAGENTA_EX}MEMORY{colorama.Fore.RESET}",
                    f"{colorama.Fore.LIGHTMAGENTA_EX}GPU{colorama.Fore.RESET}",
                    f"{colorama.Fore.LIGHTMAGENTA_EX}PURCHASE TYPE{colorama.Fore.RESET}",
                    f"{colorama.Fore.LIGHTMAGENTA_EX}MAXIMUM{colorama.Fore.RESET}",
                    f"{colorama.Fore.LIGHTMAGENTA_EX}STATUS{colorama.Fore.RESET}"
                ]
                table_rows = []
                for limit in response.json()["limits"]:
                    availability_issues_at = pretty_date(
                        round(limit["availability_issues_at"] / 1000)) if limit.get("availability_issues_at") else ""
                    table_rows.append([
                        limit["region_name"],
                        limit["instance_type"],
                        limit["resources"]["cpu"]["count"] if limit.get("resources") else "",
                        str(int(limit["resources"]["memory_mib"] / 1024)) + "GiB" if limit.get("resources") else "",
                        __pretty_print_gpu_resources(limit["resources"]) if limit.get("resources") else "",
                        limit["purchase_type"],
                        limit["maximum"],
                        f"{colorama.Fore.RED}{'No capacity ' + availability_issues_at}{colorama.Fore.RESET}" if limit.get(
                            "availability_issues_message") else f"{colorama.Fore.GREEN}OK{colorama.Fore.RESET}"
                    ])
                print(tabulate(table_rows, headers=table_headers, tablefmt="plain"))
            else:
                response.raise_for_status()
        except ConfigurationError:
            sys.exit(f"Call 'dstack config' first")


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("on-demand", help="Manage on-demand settings")

    subparsers = parser.add_subparsers()

    status_parser = subparsers.add_parser("status", help="Show if on-demand runners is enabled")
    status_parser.set_defaults(func=status_func)

    limits_parser = subparsers.add_parser("limits", help="Show limits")
    limits_parser.add_argument("--delete-all", help="Delete all limits", action="store_true")
    limits_parser.add_argument("--force", "-f", help="Don't ask for confirmation", action="store_true")
    limits_parser.set_defaults(func=limits_func)

    disable_parser = subparsers.add_parser("disable", help="Disable on-demand runners")
    disable_parser.add_argument("--force", "-f", help="Don't ask for confirmation", action="store_true")
    disable_parser.set_defaults(func=disable_func)

    enable_parser = subparsers.add_parser("enable", help="Enable on-demand runners")
    enable_parser.set_defaults(func=enable_func)

    limit_parser = subparsers.add_parser("limit", help="Change limit")
    limit_parser.add_argument("--region", "-r", type=str, help="Region name", required=False)
    limit_parser.add_argument("--instance-type", "-i", type=str, help="Instance type", required=True)
    limit_parser.add_argument("--spot", action="store_true", help="Spot purchase type",
                              default=False, required=False)
    limit_parser.add_argument("--max", "-m", type=str, help="Maximum number of instances", required=False)
    limit_parser.add_argument("--delete", help="Delete limit", action="store_true")
    limit_parser.add_argument("--force", "-f", help="Don't ask for confirmation", action="store_true")
    limit_parser.set_defaults(func=limit_func)
