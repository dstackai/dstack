import json
import os
import sys
from pathlib import Path

import requests as requests
import yaml


def submit(job_data, workflow_data, server, token):
    headers = {
        "Content-Type": f"application/json; charset=utf-8",
        "Authorization": f"Bearer {token}"
    }
    request_json = {
        "user_name": workflow_data["user_name"],
        "run_name": workflow_data["run_name"],
        "workflow_name": workflow_data["workflow_name"],
        "previous_job_ids": workflow_data.get("previous_job_ids") or None,
        "repo_url": workflow_data["repo_url"],
        "repo_branch": workflow_data["repo_branch"],
        "repo_hash": workflow_data["repo_hash"],
        "repo_diff": workflow_data.get("repo_diff") or None,
        "variables": workflow_data.get("variables") or None,
        "artifacts": job_data.get("artifacts") or None,
        "resources": job_data.get("resources") or None,
        "image_name": job_data["image_name"],
        "commands": job_data["commands"],
        "ports": job_data.get("ports") or None,
        "working_dir": job_data.get("working_dir") or None
    }
    print("Request: " + str(request_json))
    response = requests.request(method="POST", url=f"{server}/jobs/submit",
                                data=json.dumps(request_json).encode("utf-8"),
                                headers=headers)
    if response.status_code != 200:
        response.raise_for_status()
    response_json = response.json()
    print("Response: " + str(response_json))
    if response.status_code == 200:
        return response_json.get("job_id")
    else:
        response.raise_for_status()


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


def get_resources(workflow_data):
    if workflow_data.get("resources"):
        resources = {}
        if workflow_data["resources"].get("cpu"):
            if type(workflow_data["resources"]["cpu"]) is not int:
                sys.exit("resources.cpu in workflows.yaml should be an integer")
            resources["cpu"] = {
                "count": workflow_data["resources"]["cpu"]
            }
        if workflow_data["resources"].get("memory"):
            resources["memory"] = workflow_data["resources"]["memory"]
        if type(workflow_data["resources"].get("gpu")) is int:
            resources["cpu"] = {
                "count": workflow_data["resources"]["gpu"]
            }
        for resource_name in workflow_data["resources"]:
            if resource_name.endswith("/gpu") and len(resource_name) > 4:
                if type(workflow_data["resources"][resource_name]) is not int:
                    sys.exit(f"resources.'{resource_name}' in workflows.yaml should be an integer")
                resources["gpu"] = {
                    "name": resource_name[:-4],
                    "count": workflow_data["resources"][resource_name]
                }
        return resources
    else:
        return None
