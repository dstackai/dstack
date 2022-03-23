import os
import sys

from common import read_workflow_data, submit, get_resources


if __name__ == '__main__':
    workflow_data = read_workflow_data()

    if not workflow_data.get("python_script"):
        sys.exit("python_script in workflows.yaml is not specified")
    python_script = workflow_data["python_script"]
    python_version = workflow_data.get("python") or "3.10"
    if python_version not in ["3.10", "3.9", "3.8", "3.7"]:
        sys.exit("python_script in workflows.yaml must be one of ['3.10', '3.9', '3.8', '3.7']")
    environment = workflow_data.get("environment") or {}
    commands = []
    python_requirements_specified = workflow_data.get("requirements")
    if python_requirements_specified:
        commands.append("pip install -r " + workflow_data["requirements"])
    environment_init = ""
    if environment:
        for name in environment:
            escaped_value = environment[name].replace('"', '\\"')
            environment_init += f"{name}=\"{escaped_value}\" "
    commands.append(
        f"{environment_init}python {python_script}"
    )
    resources = get_resources(workflow_data)
    gpu = resources and resources.get("gpu") and resources.get("gpu").get("count") > 0
    job_data = {
        "image_name": f"dstackai/python:{python_version}-cuda-11.6.0" if gpu else f"python:{python_version}",
        "commands": commands
    }
    if workflow_data.get("artifacts"):
        job_data["artifacts"] = workflow_data["artifacts"]
    if workflow_data.get("working_dir"):
        job_data["working_dir"] = workflow_data["working_dir"]
    if resources:
        job_data["resources"] = resources
    # TODO: Handle ports
    submit(job_data, workflow_data, os.environ["DSTACK_SERVER"], os.environ["DSTACK_TOKEN"])