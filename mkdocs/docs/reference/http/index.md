---
title: HTTP API
hide:
  - toc
---

The HTTP API enables running tasks, services, and managing runs programmatically.

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

## Reference

The HTTP API reference is split by endpoint tag.

<!-- BEGIN GENERATED HTTP API TAGS -->
- [server](server.md)
- [users](users.md)
- [authentication](authentication.md)
- [projects](projects.md)
- [backends](backends.md)
- [fleets](fleets.md)
- [repos](repos.md)
- [runs](runs.md)
- [gpus](gpus.md)
- [metrics](metrics.md)
- [logs](logs.md)
- [secrets](secrets.md)
- [gateways](gateways.md)
- [volumes](volumes.md)
- [proxy](proxy.md)
- [files](files.md)
- [events](events.md)
- [templates](templates.md)
- [exports](exports.md)
- [default](default.md)
<!-- END GENERATED HTTP API TAGS -->
