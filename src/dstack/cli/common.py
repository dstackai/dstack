import collections
import os
import re
import sys
import typing as ty
from pathlib import Path

import giturlparse
import yaml
from git import Repo
from paramiko.config import SSHConfig
from rich import box
from rich.console import Console
from rich.table import Table


def load_variables():
    root_folder = Path(os.getcwd()) / ".dstack"
    if root_folder.exists():
        variable_file = root_folder / "variables.yaml"
        if variable_file.exists():
            variable_root = yaml.load(variable_file.open(), Loader=yaml.FullLoader)
            variables = variable_root.get("variables")
            return variables
        else:
            return dict()
    else:
        return []


def load_repo_data():
    # TODO: Allow to override the current working directory, e.g. via --dir
    cwd = os.getcwd()
    repo = Repo(cwd)
    tracking_branch = repo.active_branch.tracking_branch()
    if tracking_branch:
        repo_branch = tracking_branch.remote_head
        remote_name = tracking_branch.remote_name
        repo_hash = tracking_branch.commit.hexsha
        repo_url = repo.remote(remote_name).url

        repo_url_parsed = giturlparse.parse(repo_url)

        if repo_url_parsed.protocol == "ssh":
            ssh_config_path = os.path.expanduser('~/.ssh/config')
            if os.path.exists(ssh_config_path):
                fp = open(ssh_config_path, 'r')
                config = SSHConfig()
                config.parse(fp)
                repo_url = repo_url.replace(repo_url_parsed.resource,
                                            config.lookup(repo_url_parsed.resource)['hostname'])
                # TODO: Detect and pass private key too
                fp.close()

        # TODO: Doesn't support unstaged changes
        repo_diff = repo.git.diff(repo_hash)
        result = re.compile("^(https://|git@)github.com/([^/]+)/([^.]+)(\\.git)?$").match(repo_url)
        if result:
            repo_user_name = result.group(2)
            repo_name = result.group(3)
            return repo_user_name, repo_name, repo_branch, repo_hash, repo_diff
        else:
            sys.exit(f"{os.getcwd()} is not a GitHub repo")
    else:
        sys.exit(f"No tracked branch configured for branch {repo.active_branch.name}")


def load_workflows():
    root_folder = Path(os.getcwd()) / ".dstack"
    if root_folder.exists():
        workflows_file = root_folder / "workflows.yaml"
        if workflows_file.exists():
            return yaml.load(workflows_file.open(), Loader=yaml.FullLoader)
        else:
            return None
    else:
        return None


def load_providers():
    root_folder = Path(os.getcwd()) / ".dstack"
    if root_folder.exists():
        providers_file = root_folder / "providers.yaml"
        if providers_file.exists():
            return yaml.load(providers_file.open(), Loader=yaml.FullLoader)
        else:
            return None
    else:
        return None


def pretty_date(time: ty.Any = False):
    """
    Get a datetime object or a int() Epoch timestamp and return a
    pretty string like 'an hour ago', 'Yesterday', '3 months ago',
    'just now', etc
    """
    from datetime import datetime
    now = datetime.now()
    if type(time) is int:
        diff = now - datetime.fromtimestamp(time)
    elif isinstance(time, datetime):
        diff = now - time
    elif not time:
        diff = now - now
    second_diff = diff.seconds
    day_diff = diff.days

    if day_diff < 0:
        return ''

    if day_diff == 0:
        if second_diff < 10:
            return "now"
        if second_diff < 60:
            return str(second_diff) + " sec ago"
        if second_diff < 120:
            return "1 min ago"
        if second_diff < 3600:
            return str(round(second_diff / 60)) + " mins ago"
        if second_diff < 7200:
            return "1 hour ago"
        if second_diff < 86400:
            return str(round(second_diff / 3600)) + " hours ago"
    if day_diff == 1:
        return "yesterday"
    if day_diff < 7:
        return str(day_diff) + " days ago"
    if day_diff < 31:
        return str(round(day_diff / 7)) + " weeks ago"
    if day_diff < 365:
        return str(round(day_diff / 30)) + " months ago"
    return str(round(day_diff / 365)) + " years ago"


def __flatten(d, parent_key='', sep='.'):
    items = []
    for k, v in d.items():
        new_key = parent_key + sep + k if parent_key else k
        if isinstance(v, collections.MutableMapping):
            items.extend(__flatten(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def pretty_variables(variables):
    if len(variables) > 0:
        variables_str = ""
        for k, v in __flatten(variables).items():
            if len(variables_str) > 0:
                variables_str += "\n"
            variables_str = variables_str + "--" + k + " " + str(v)
        return variables_str
    else:
        return ""


colors = {
    "SUBMITTED": "yellow",
    "QUEUED": "yellow",
    "RUNNING": "green",
    "DONE": "grey58",
    "FAILED": "red",
    "STOPPED": "grey58",
    "STOPPING": "yellow",
    "ABORTING": "yellow",
    "ABORTED": "grey58",
    "REQUESTED": "yellow",
}


def colored(status: str, val: str, bright: bool = False):
    color = colors.get(status)
    return f"[{'bold' if bright else ''}{color}]{val}[/]" if color is not None else val


def print_runners(profile):
    runners = get_runners(profile)
    console = Console()

    table = Table(box=box.SQUARE)
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
