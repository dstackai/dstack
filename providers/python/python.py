import os
import sys

from common import read_workflow_data, submit

if __name__ == '__main__':
    workflow_data = read_workflow_data()

    if not workflow_data.get("python_script"):
        sys.exit("python_script in workflows.yaml is not specified")
    python_script = workflow_data["python_script"]
    python_version = workflow_data.get("python") or "3.9"
    commands = []
    python_requirements_specified = workflow_data.get("requirements")
    if python_requirements_specified:
        commands.append("pip3 install -r " + workflow_data["requirements"])
    commands.append(
        f"python3 {python_script}"
    )
    artifacts = workflow_data["artifacts"] if workflow_data.get("artifacts") else None
    working_dir = workflow_data["working_dir"] if workflow_data.get("working_dir") else None
    job = {
        "image_name": f"python:{python_version}",
        "commands": commands,
        "ports": None,
        "resources": None,
        "working_dir": working_dir,
        "artifacts": [a for a in artifacts] if artifacts else None
    }
    submit(job, workflow_data, os.environ["DSTACK_SERVER"], os.environ["DSTACK_TOKEN"])