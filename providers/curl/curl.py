import os
import sys

from common import read_workflow_data, submit

if __name__ == '__main__':
    workflow_data = read_workflow_data()

    if not workflow_data.get("url"):
        sys.exit("url in workflows.yaml is not specified")
    if not workflow_data.get("output"):
        sys.exit("output in workflows.yaml is not specified")
    url = workflow_data["url"]
    output = workflow_data["output"]
    commands = [
        f"curl {url} -o {output}"
    ]
    job_data = {
        "image_name": f"python:3.9",
        "commands": commands
    }
    if workflow_data.get("artifacts"):
        job_data["artifacts"] = workflow_data["artifacts"]
    if workflow_data.get("working_dir"):
        job_data["working_dir"] = workflow_data["working_dir"]
    submit(job_data, workflow_data, os.environ["DSTACK_SERVER"], os.environ["DSTACK_TOKEN"])