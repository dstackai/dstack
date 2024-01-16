# Serving LLMs using Python API

The [Python API](../docs/reference/api/python/index.md) of `dstack` can be used to run [tasks](../docs/concepts/tasks.md) and [services](../docs/concepts/services.md) programmatically.

To demonstrate how it works, we've created a simple Streamlit app that uses `dstack`'s API to deploy a quantized 
version of Llama 2 to your cloud with a click of a button.

![](images/python-api/dstack-python-api-streamlit-example.png){ width=800 }

## Prerequisites

Before you can use `dstack` Python API, ensure you have  
[set up the server](../docs/index.md#set-up-the-server).

## How does it work?

### Create a client

If you're familiar with Docker's Python SDK, you'll find `dstack`'s [Python API](../docs/reference/api/python/index.md) 
quite similar, except that it runs your workload in the cloud.

To get started, create an instance of `dstack.Client` and use its methods to submit and manage runs.

```python
from dstack.api import Client, ClientError

try:
    client = Client.from_config()
except ClientError as e:
    print(e)
```

### Create a task

!!! info "NOTE:"
    With `dstack.Client`, you can run [tasks](../docs/concepts/tasks.md) and [services](../docs/concepts/services.md).
    Running a task allows you to programmatically access its ports and
    forward traffic to your local machine. For example, if you run an LLM as a task, you can access it on `localhost`.
    Services on the other hand allow deploying applications as public endpoints.

In our example, we'll deploy an LLM as a task. To do this, we'll create a `dstack.Task` instance that configures how the
LLM should be run.

```python
from dstack.api import Task

configuration = Task(
    image="ghcr.io/huggingface/text-generation-inference:latest",
    env={"MODEL_ID": model_id},
    commands=[
        "text-generation-launcher --trust-remote-code --quantize gptq",
    ],
    ports=["8080:80"],  # LLM runs on port 80, forwarded to localhost:8080
)
```

### Create resources

Then, we'll need to specify the resources our LLM will require. To do this, we'll create a `dstack.Resources` instance:

```python
from dstack.api import Resources, GPU

if model_id == "TheBloke/Llama-2-13B-chat-GPTQ":
    gpu_memory = "20GB"
elif model_id == "TheBloke/Llama-2-70B-chat-GPTQ":
    gpu_memory = "40GB"

resources = Resources(gpu=GPU(memory=gpu_memory))
```

### Submit the run

To deploy the LLM, we submit the task using `runs.submit()` in `dstack.Client`.

```python
run_name = "deploy-python"

run = client.runs.submit(configuration=configuration, run_name=run_name, resources=resources)
```

### Attach to the run

Then, we use the `attach()` method on `dstack.Run`. This method waits for the task to start, 
and forwards the configured ports to `localhost`.

```
run.attach()
```

### Wait for the endpoint to start

Finally, we wait until `http://localhost:8080/health` returns `200`, which indicates that the LLM is deployed and ready to
handle requests.

```python
import time
import requests

while True:
    time.sleep(0.5)
    try:
        r = requests.get("http://localhost:8080/health")
        if r.status_code == 200:
            break
    except Exception:
        pass
```

### Stop the run

To undeploy the model, we can use the `stop()` method on `dstack.Run`.

```python
run.stop()
```

### Retrieve the status of a run

Note: If you'd like to retrieve the `dstack.Run` instance by the name of the run,
you can use the `runs.get()` method on `dstack.Client`.

```python
run = client.runs.get(run_name)
```

The `status` property on `dstack.Run` provides the status of the run.

```python
if run:
    print(run.status)
```

To get the latest state of the run, you can use the `run.refresh()` method:

```python
run.refresh()
```

## Source code
    
The complete, ready-to-run code is available in [dstackai/dstack-examples](https://github.com/dstackai/dstack-examples).

```shell
git clone https://github.com/dstackai/dstack-examples
cd dstack-examples
```

Once the repository is cloned, feel free to install the requirements and run the app:

```
pip install -r deploy-python/requirements.txt
streamlit run deploy-python/app.py
```