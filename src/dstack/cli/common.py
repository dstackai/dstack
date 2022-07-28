import collections
import json
import os
import sys
import typing as ty
from pathlib import Path

import boto3
import giturlparse
import yaml
from git import Repo
from paramiko.config import SSHConfig
from requests import request
from rich import box
from rich.console import Console
from rich.table import Table


from dstack.config import get_config


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
        return repo_url, repo_branch, repo_hash, repo_diff
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


def headers_and_params(profile, run_name, require_repo=True):
    headers = {}
    if profile.token is not None:
        headers["Authorization"] = f"Bearer {profile.token}"
    params = {
    }
    try:
        repo_url, _, _, _ = load_repo_data()
        params["repo_url"] = repo_url
    except Exception as e:
        if require_repo:
            raise e
    if run_name is not None:
        params["run_name"] = run_name
    return headers, params


def get_runs(run_name: ty.Optional[str], workflow_name: ty.Optional[str], profile):
    headers, params = headers_and_params(profile, run_name, False)
    # del params["repo_url"]
    if workflow_name:
        params["workflow_name"] = workflow_name
    response = request(method="GET", url=f"{profile.server}/runs/workflows/query", params=params, headers=headers,
                       verify=profile.verify)
    response.raise_for_status()
    runs = list(reversed(response.json()["runs"]))
    return runs


# TODO: Add a parameter repo_url
def get_jobs(run_name: ty.Optional[str], profile):
    headers, params = headers_and_params(profile, run_name, True)
    response = request(method="GET", url=f"{profile.server}/jobs/query", params=params, headers=headers,
                       verify=profile.verify)
    response.raise_for_status()
    jobs = sorted(response.json()["jobs"], key=lambda job: (job["updated_at"]))
    return jobs


def get_runners(profile):
    headers, params = headers_and_params(profile, None, require_repo=False)
    response = request(method="GET", url=f"{profile.server}/runners/query", params=params, headers=headers,
                       verify=profile.verify)
    response.raise_for_status()
    runs = sorted(response.json()["runners"], key=lambda job: (job["updated_at"]))
    return runs


def get_job(job_id, profile):
    headers, params = headers_and_params(profile, None)
    response = request(method="GET", url=f"{profile.server}/jobs/{job_id}", params=params, headers=headers,
                       verify=profile.verify)
    if response.status_code == 200:
        return response.json()["job"]
    elif response.status_code == 404:
        return None
    else:
        response.raise_for_status()


def pretty_repo_url(repo_url):
    r = repo_url
    if r.endswith(".git"):
        r = r[:-4]
    if r.startswith("https://github.com"):
        r = r[19:]
    return r


def get_runner_name(run_or_job):
    if run_or_job["runner_name"]:
        if run_or_job.get("runner_user_name") and run_or_job["runner_user_name"] != run_or_job["user_name"]:
            runner_name = run_or_job["runner_name"] + "@" + run_or_job["runner_user_name"]
        else:
            runner_name = run_or_job["runner_name"]
    else:
        runner_name = "<none>"
    return runner_name


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


def pretty_print_status(workflow: dict) -> str:
    status = workflow["status"].upper()
    availability_issues = workflow.get("availability_issues")
    if availability_issues:
        return "No capacity"
    if status == "SUBMITTED":
        return "Provisioning..."
    if status == "QUEUED":
        return "Provisioning..."
    if status == "RUNNING":
        return "Running..."
    if status == "DONE":
        return "Done"
    if status == "FAILED":
        return "Failed"
    if status == "STOPPING":
        return "Stopping..."
    if status == "ABORTING":
        return "Aborting..."
    if status == "STOPPED":
        return "Stopped"
    if status == "ABORTED":
        return "Aborted"
    if status == "REQUESTED":
        return "Provisioning..."


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


def __job_ids(ids):
    if ids is not None:
        return ", ".join(ids)
    else:
        return ""


def short_artifact_path(path):
    # The format of the path is <user_name>/<run_name>/<job_id>/<internal_artifact_path>
    return '/'.join(path.split('/')[3:])


def list_artifact(client, artifacts_s3_bucket, artifact_path):
    response = client.list_objects(Bucket=artifacts_s3_bucket, Prefix=artifact_path)

    keys_count = 0
    total_size = 0
    for obj in response.get("Contents") or []:
        keys_count += 1
        total_size += obj["Size"]
    return keys_count, total_size


def list_artifact_files(client, artifacts_s3_bucket, artifact_path):
    response = client.list_objects(Bucket=artifacts_s3_bucket, Prefix=artifact_path)

    return [(obj["Key"][len(artifact_path):].lstrip("/"), obj["Size"]) for obj in
            (response.get("Contents") or [])]


def get_user_info(profile):
    headers = {}
    if profile.token is not None:
        headers["Authorization"] = f"Bearer {profile.token}"
    params = {}
    response = request(method="POST", url=f"{profile.server}/users/info", params=params, headers=headers,
                       verify=profile.verify)
    response.raise_for_status()
    return response.json()


def boto3_client(user_info: dict, service_name: str, job: ty.Optional[dict] = None):
    configuration = user_info["user_configuration"] if service_name == "s3" and user_info.get(
        "user_configuration") is not None and job is not None and job["user_artifacts_s3_bucket"] is not None else \
        user_info["default_configuration"]
    # if configuration.get("aws_session_token") is not None:
    #     client = boto3.client(service_name, aws_access_key_id=configuration["aws_access_key_id"],
    #                           aws_secret_access_key=configuration["aws_secret_access_key"],
    #                           aws_session_token=configuration["aws_session_token"],
    #                           region_name=configuration["aws_region"])
    # else:
    return boto3.client(service_name, aws_access_key_id=configuration["aws_access_key_id"],
                        aws_secret_access_key=configuration["aws_secret_access_key"],
                        region_name=configuration["aws_region"])


def sensitive(value: ty.Optional[str]):
    if value:
        return value[:4] + ((len(value) - 8) * "*") + value[-4:]
    else:
        return None


def do_post(api, data=None):
    dstack_config = get_config()
    profile = dstack_config.get_profile("default")
    headers = {}
    if profile.token is not None:
        headers["Authorization"] = f"Bearer {profile.token}"
    if data is not None:
        data_bytes = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = f"application/json; charset=utf-8"
        response = request(method="POST", url=f"{profile.server}/{api}", data=data_bytes, headers=headers,
                           verify=profile.verify)
    else:
        response = request(method="POST", url=f"{profile.server}/{api}", headers=headers,
                           verify=profile.verify)
    return response


def do_get(api, params=None):
    if params is None:
        params = {}
    dstack_config = get_config()
    profile = dstack_config.get_profile("default")
    headers = {}
    if profile.token is not None:
        headers["Authorization"] = f"Bearer {profile.token}"
    response = request(method="GET", url=f"{profile.server}/{api}", params=params, headers=headers,
                       verify=profile.verify)
    return response
