import sys
from argparse import Namespace

from dstack.cli.common import colored
from rich.console import Console
from rich.table import Table

def print_runners(profile):
    runners = get_runners(profile)
    console = Console()

    table = Table()
    table.add_column("Runner", style="bold", no_wrap=True)
    table.add_column("Host", style="grey58", width=24)
    table.add_column("CPU", style="grey58", width=4)
    table.add_column("Memory", style="grey58", width=8)
    table.add_column("GPU", style="grey58", width=6)
    table.add_column("Status", style="grey58", width=12)

    for runner in runners:
        status = runner["status"].upper()
        table.add_row(colored(status, runner["runner_name"]),
                      runner.get("host_name"),
                      runner["resources"]["cpu"]["count"],
                      str(int(runner["resources"]["memory_mib"] / 1024)) + "GiB",
                      __pretty_print_gpu_resources(runner["resources"]),
                      colored(status, status))

    console.print(table)


def __pretty_print_gpu_resources(resources):
    gpus = {}
    for g in resources["gpus"]:
        if g["name"] in gpus:
            gpus[g["name"]] = gpus[g["name"]]["count"] + 1
        else:
            gpus[g["name"]] = {
                "count": 1,
                "memory_mib": g["memory_mib"]
            }
    _str = ""
    for g in gpus:
        if len(_str) > 0:
            _str = _str + "\n"
        gb = str(int(gpus[g]["memory_mib"] / 1024)) + "GiB"
        _str = _str + g + " " + gb + " x " + str(gpus[g]["count"])
    return _str if len(_str) > 0 else "<none>"


def runners_func(_: Namespace):
    try:
        dstack_config = get_config()
        # TODO: Support non-default profiles
        profile = dstack_config.get_profile("default")
        print_runners(profile)
    except ConfigurationError:
        sys.exit(f"Call 'dstack config' first")


def register_parsers(main_subparsers):
    parser = main_subparsers.add_parser("runners", help="Show runners")

    parser.set_defaults(func=runners_func)
