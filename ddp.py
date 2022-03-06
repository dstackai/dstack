import os
import sys

from common import read_workflow_data, submit

if __name__ == '__main__':
    workflow_data = read_workflow_data()

    if not workflow_data.get("resources") \
            or not workflow_data["resources"].get("nodes"):
        sys.exit("resources.nodes in workflows.yaml is not specified")
    if type(workflow_data["resources"].get("nodes")) is not int \
            or workflow_data["resources"]["nodes"] < 2:
        sys.exit("resources.nodes in workflows.yaml should be an integer > 1")
    if not workflow_data.get("training_script"):
        sys.exit("training_script in workflows.yaml is not specified")
    nnode = workflow_data["resources"]["nodes"]
    training_script = workflow_data["training_script"]
    # create 1 master job
    # create nodes - 1 jobs that refer to the master job
    if workflow_data.get("python"):
        python_version = workflow_data["python"]
    else:
        python_version = "3.9"
    master_commands = []
    python_requirements_specified = workflow_data.get("requirements")
    if python_requirements_specified:
        master_commands.append("pip3 install -r " + workflow_data["requirements"])
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
        "requirements": None,
        "working_dir": workflow_data["working_dir"] if workflow_data.get(
            "working_dir") else None
    }
    submit(master_job, workflow_data, os.environ["DSTACK_SERVER"], os.environ["DSTACK_TOKEN"])
    for index in range(nnode - 1):
        dependent_commands = []
        if python_requirements_specified:
            dependent_commands.append("pip3 install -r " + workflow_data["requirements"])
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
            "image": f"python:{python_version}", "commands": dependent_commands,
            "ports": None,
            "resources": None,
            "working_dir": workflow_data["working_dir"] if workflow_data.get("working_dir") else None
        }
        submit(dependent_job, workflow_data, os.environ["DSTACK_SERVER"], os.environ["DSTACK_TOKEN"])
