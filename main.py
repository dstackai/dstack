import os
from pathlib import Path

import yaml

if __name__ == '__main__':
    print("DSTACK_SERVER: " + str(os.environ.get("DSTACK_SERVER")))
    print("DSTACK_TOKEN: " + str(os.environ.get("DSTACK_TOKEN")))
    print("REPO_PATH: " + str(os.environ.get("REPO_PATH")))
    workflow_file = Path("workflow.yaml")
    if workflow_file.is_file():
        with workflow_file.open() as f:
            print("WORKFLOW: " + str(yaml.load(f, yaml.FullLoader)))
    else:
        print("workflow.yaml is missing")
