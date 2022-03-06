import json
import os
import sys
from pathlib import Path

import requests as requests
import yaml


def submit(job, workflow_data, server, token):
    headers = {
        "Content-Type": f"application/json; charset=utf-8",
        "Authorization": f"Bearer {token}"
    }
    request_json = {
        "user_name": workflow_data["user_name"],
        "run_name": workflow_data["run_name"],
        "workflow_name": workflow_data["workflow_name"],
        "previous_job_ids": workflow_data.get("previous_job_ids"),
        "repo_url": workflow_data["repo_url"],
        "repo_branch": workflow_data["repo_branch"],
        "repo_hash": workflow_data["repo_hash"],
        "repo_diff": workflow_data.get("repo_diff"),
        "variables": workflow_data.get("variables"),
        "resources": job.get("resources"),
        "image": job["image"],
        "commands": job["commands"],
        "ports": job.get("ports"),
        "working_dir": workflow_data.get("working_dir")
    }
    print("Request: " + str(request_json))
    response = requests.request(method="POST", url=f"{server}/jobs/submit",
                                data=json.dumps(request_json).encode("utf-8"),
                                headers=headers)
    if response.status_code != 200:
        response.raise_for_status()
    response_json = response.json()
    print("Response: " + str(response_json))
    return response_json.get("job_id")


def read_workflow_data():
    if not os.environ.get("DSTACK_SERVER"):
        sys.exit("DSTACK_SERVER environment variable is not specified")
    if not os.environ.get("DSTACK_TOKEN"):
        sys.exit("DSTACK_SERVER environment variable is not specified")
    if not os.environ.get("REPO_PATH"):
        sys.exit("REPO_PATH environment variable is not specified")
    if not os.path.isdir(os.environ["REPO_PATH"]):
        sys.exit("REPO_PATH environment variable doesn't point to a valid directory: " + os.environ["REPO_PATH"])
    workflow_file = Path("workflow.yaml")
    if not workflow_file.is_file():
        sys.exit("workflow.yaml is missing")
    with workflow_file.open() as f:
        return yaml.load(f, yaml.FullLoader)
