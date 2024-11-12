# Text Generation Inference

This example shows how to deploy `mistralai/Mistral-7B-Instruct-v0.2` with `dstack` using [TGI :material-arrow-top-right-thin:{ .external }](https://huggingface.co/docs/text-generation-inference/en/index)

??? info "Prerequisites"
    Once `dstack` is [installed](https://dstack.ai/docs/installation), go ahead clone the repo, and run `dstack init`.

    <div class="termy">
 
    ```shell
    $ git clone https://github.com/dstackai/dstack
    $ cd dstack
    $ dstack init
    ```
 
    </div>

## Deployment

### Running as a task
If you'd like to run mistralai/Mistral-7B-Instruct-v0.2 for development purposes, consider using `dstack` [tasks](https://dstack.ai/docs/tasks/).
<div editor-title="examples/deployment/tgi/serve-task.dstack.yml">

```yaml
type: task
# This task runs Llama 2 with TGI

image: ghcr.io/huggingface/text-generation-inference:latest
env:
  - HF_TOKEN
  - MODEL_ID=mistralai/Mistral-7B-Instruct-v0.2
commands:
  - text-generation-launcher --port 8000 --trust-remote-code
ports:
  - 8000

resources:
  gpu: 24GB
```
</div>

### Deploying as a service

If you'd like to deploy the model as an auto-scalable and secure endpoint,
use the [service](https://dstack.ai/docs/services) configuration. You can find it at [`examples/deployment/tgi/serve.dstack.yml` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/deployment/tgi/serve.dstack.yml)

### Running a configuration

To run a configuration, use the [`dstack apply`](https://dstack.ai/docs/reference/cli/index.md#dstack-apply) command. 

<div class="termy">

```shell
$ HF_TOKEN=...
$ dstack apply -f examples/deployment/tgi/serve-task.dstack.yml

 #  BACKEND     REGION        RESOURCES                      SPOT  PRICE    
 1  tensordock  unitedstates  2xCPU, 10GB, 1xRTX3090 (24GB)  no    $0.231   
 2  tensordock  unitedstates  2xCPU, 10GB, 1xRTX3090 (24GB)  no    $0.242   
 3  tensordock  india         2xCPU, 38GB, 1xA5000 (24GB)    no    $0.283  

Submit a new run? [y/n]: y

Provisioning...
---> 100%
```
</div>

## Source code

The source-code of this example can be found in 
[`examples/deployment/tgi` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/deployment/tgi).

## What's next?

1. Check [dev environments](https://dstack.ai/docs/dev-environments), [tasks](https://dstack.ai/docs/tasks), 
   [services](https://dstack.ai/docs/services), and [protips](https://dstack.ai/docs/protips).
2. Browse [Deployment on AMD :material-arrow-top-right-thin:{ .external }](https://dstack.ai/examples/accelerators/amd/) and
   [Deployment on TPU :material-arrow-top-right-thin:{ .external }](https://dstack.ai/examples/accelerators/tpu/).