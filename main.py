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
    data = {
        "user_name": workflow_data["user_name"],
        "run_name": workflow_data["run_name"],
        "workflow_name": workflow_data["workflow_name"],
        "previous_job_ids": workflow_data["previos_job_ids"],
        "repo_url": workflow_data["repo_url"],
        "repo_branch": workflow_data["repo_branch"],
        "repo_hash": workflow_data["repo_hash"],
        "repo_diff": workflow_data["repo_diff"],
        "variables": workflow_data["variables"],
        "resources": job.resources,
        "image": job.image,
        "commands": job.commands,
        "ports": job.ports
    }
    response = requests.request(method="POST", url=f"{server}/jobs/stop",
                                data=json.dumps(data).encode("utf-8"),
                                headers=headers)
    if response.status_code != 200:
        response.raise_for_status()
    return response.json().get("job_id")


if __name__ == '__main__':
    if not os.environ.get("DSTACK_SERVER"):
        sys.exit("DSTACK_SERVER environment variable is not specified")
    if not os.environ.get("DSTACK_TOKEN"):
        sys.exit("DSTACK_SERVER environment variable is not specified")
    if not os.environ.get("REPO_PATH"):
        sys.exit("REPO_PATH environment variable is not specified")
    if not os.path.isdir(os.environ["REPO_PATH"]):
        sys.exit("REPO_PATH environment variable doesn't point to a valid directory: " + os.environ["REPO_PATH"])
    workflow_file = Path("workflow.yaml")
    if workflow_file.is_file():
        with workflow_file.open() as f:
            workflow_data = yaml.load(f, yaml.FullLoader)
        if not workflow_data.get("params") or not workflow_data["params"].get("nodes") or not workflow_data["params"][
            "nodes"].get("count"):
            sys.exit("params.nodes.count in workflows.yaml is not specified")
        if workflow_data["params"]["nodes"].get("count") is not int or workflow_data["params"]["nodes"]["count"] < 2:
            sys.exit("params.nodes.count in workflows.yaml should be an integer > 1")
        print("WORKFLOW DATA: " + str(workflow_data))
        nodes = workflow_data.params.nodes.count
        # create 1 master job
        # create nodes - 1 jobs that refer to the master job
    else:
        sys.exit("workflow.yaml is missing")
