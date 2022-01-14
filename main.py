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
        "previous_job_ids": workflow_data["previous_job_ids"],
        "repo_url": workflow_data["repo_url"],
        "repo_branch": workflow_data["repo_branch"],
        "repo_hash": workflow_data["repo_hash"],
        "repo_diff": workflow_data["repo_diff"],
        "variables": workflow_data["variables"],
        "resources": job.resources,
        "image": job.image,
        "commands": job.commands,
        "ports": job.ports,
        "working_dir": workflow_data["working_dir"]
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
    if not workflow_file.is_file():
        sys.exit("workflow.yaml is missing")

    with workflow_file.open() as f:
        workflow_data = yaml.load(f, yaml.FullLoader)
    if not workflow_data.get("params") or not workflow_data["params"].get("nodes") \
            or not workflow_data["params"]["nodes"].get("count"):
        sys.exit("params.nodes.count in workflows.yaml is not specified")
    if type(workflow_data["params"]["nodes"].get("count")) is not int \
            or workflow_data["params"]["nodes"]["count"] < 2:
        sys.exit("params.nodes.count in workflows.yaml should be an integer > 1")
    if not workflow_data["params"].get("training_script"):
        sys.exit("params.training_script in workflows.yaml is not specified")
    print("WORKFLOW DATA: " + str(workflow_data))
    nnode = workflow_data["params"]["nodes"]["count"]
    training_script = workflow_data["params"]["training_script"]
    # create 1 master job
    # create nodes - 1 jobs that refer to the master job
    if workflow_data.get("python") and workflow_data.get["python"].get("version"):
        python_version = workflow_data["python"]["version"]
    else:
        python_version = "3.9"
    master_commands = []
    python_requirements_specified = workflow_data.get("python") and workflow_data["python"].get("requirements")
    if python_requirements_specified:
        master_commands.append("pip3 install -r " + workflow_data["python"]["requirements"])
    master_commands.append(
        f"python3 -m torch.distributed.launch "
        f"--nnode={nnode} "
        f"--node_rank=0 "
        f"--nproc_per_node=1 "
        f"--master_addr=$HOST_NAME "
        f"--master_port=12345 {training_script} "
        f"--local_world_size=1"
    )
    master_job = {
        "image": f"python:{python_version}",
        "commands": master_commands,
        "ports": [12345],
        "resources": None,
        "working_dir": workflow_data["params"]["working_dir"] if workflow_data["params"].get("working_dir") else None
    }
    print("MASTER JOB:" + str(master_job))
    # submit(master_job, workflow_data, os.environ["DSTACK_SERVER"], os.environ["DSTACK_TOKEN"])
    for index in range(nnode - 1):
        dependent_commands = []
        if python_requirements_specified:
            dependent_commands.append("pip3 install -r " + workflow_data["python"]["requirements"])
        dependent_commands.append(
            f"python3 -m torch.distributed.launch "
            f"--nnode={nnode} "
            f"--node_rank={index + 1} "
            f"--nproc_per_node=1 "
            f"--master_addr=$MASTER_JOB_HOST_NAME "
            f"--master_port=$MASTER_JOB_PORT_12345 {training_script} "
            f"--local_world_size=1"
        )
        dependent_job = {
            "image": f"python:{python_version}",            "commands": dependent_commands,
            "ports": None,
            "resources": None,
            "working_dir": workflow_data["params"]["working_dir"] if workflow_data["params"].get(
                "working_dir") else None
        }
        print("DEPENDANT JOB #" + str(index + 1) + ": " + str(dependent_job))
        # submit(dependent_job, workflow_data, os.environ["DSTACK_SERVER"], os.environ["DSTACK_TOKEN"])
