import os
import sys

from common import read_workflow_data, submit, get_resources


if __name__ == '__main__':
    workflow_data = read_workflow_data()

    if not workflow_data.get("python_script"):
        sys.exit("python_script in workflows.yaml is not specified")
    python_script = workflow_data["python_script"]
    python_version = workflow_data.get("python") or "3.9"
    environment = workflow_data.get("environment") or {}
    commands = []
    python_requirements_specified = workflow_data.get("requirements")
    if python_requirements_specified:
        commands.append("pip3 install -r " + workflow_data["requirements"])
    environment_init = ""
    if environment:
        for name in environment:
            escaped_value = environment[name].replace('"', '\\"')
            environment_init += f"{name}=\"{escaped_value}\" "
    commands.append(
        f"{environment_init}python3 {python_script}"
    )
    job_data = {
        "image_name": f"python:{python_version}",
        "commands": commands
    }
    if workflow_data.get("artifacts"):
        job_data["artifacts"] = workflow_data["artifacts"]
    if workflow_data.get("working_dir"):
        job_data["working_dir"] = workflow_data["working_dir"]
    resources = get_resources(workflow_data)
    if resources:
        job_data["resources"] = resources
    # TODO: Handle ports
    submit(job_data, workflow_data, os.environ["DSTACK_SERVER"], os.environ["DSTACK_TOKEN"])