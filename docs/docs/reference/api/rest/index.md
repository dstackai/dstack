---
title: REST API
---

The REST API enables running tasks, services, and managing runs programmatically.

## Usage example

Below is a quick example of submitting a task for running and waiting for its completion.

```python
import os
from pathlib import Path
import time
import requests

url = os.environ["DSTACK_URL"]
token = os.environ["DSTACK_TOKEN"]
project = os.environ["DSTACK_PROJECT"]
ssh_public_key = Path(os.environ["SSH_PUBLIC_KEY_PATH"]).read_text()

print("Submitting task")
resp = requests.post(
    url=f"{url}/api/project/{project}/runs/apply",
    headers={"Authorization": f"Bearer {token}"},
    json={
        "plan":{
            "run_spec": {
                "configuration": {
                    "type": "task",
                    "commands": [
                        "echo Start",
                        "sleep 10", # do some work here
                        "echo Finish"
                    ],
                },
                "ssh_key_pub": ssh_public_key,
            }
        },
        "force": False,
    },
)
run_name = resp.json()["run_spec"]["run_name"]

print("Waiting for task completion")
while True:
    resp = requests.post(
        url=f"{url}/api/project/{project}/runs/get",
        headers={"Authorization": f"Bearer {token}"},
        json={"run_name": run_name}
    )
    if resp.json()["status"] in ["terminated", "aborted", "failed", "done"]:
        print(f"Run finished with status {resp.json()['status']}")
        break
    time.sleep(2)
```

<style>
    .swagger-ui .info {
        margin: 0 !important;
    }

    .swagger-ui .info h1, .swagger-ui .info h2, .swagger-ui .info h3, .swagger-ui .info h4, .swagger-ui .info h5 {
        font-weight: 800 !important;
        letter-spacing: -1px !important;
        color: rgb(0, 0, 0) !important;
        text-transform: none !important;
        font-family: var(--md-text-font-family) !important;
    }

    .swagger-ui .info .title {
        padding: 0 !important;
    }

    .swagger-ui .info li, .swagger-ui .info p, .swagger-ui .info table {
        line-height: 1.3rem !important;
        font-size: 0.8rem !important;
        font-family: var(--md-text-font-family) !important;
    }
</style>

<br></br>

!!swagger openapi.json!!
