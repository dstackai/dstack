# vLLM
This example shows how to deploy `NousResearch/Llama-2-7b-chat-hf` with `dstack` using [vLLM :material-arrow-top-right-thin:{ .external }](https://docs.vllm.ai/en/latest/)

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
If you'd like to run NousResearch/Llama-2-7b-chat-hf for development purposes, consider using `dstack` [tasks](https://dstack.ai/docs/tasks/).
<div editor-title="examples/deployment/vllm/serve-task.dstack.yml">

```yaml
type: task
# This task runs Llama 2 with vllm

image: vllm/vllm-openai:latest
env:
  - MODEL=NousResearch/Llama-2-7b-chat-hf
  - PYTHONPATH=/workspace
commands:
  - python3 -m vllm.entrypoints.openai.api_server --model $MODEL --port 8000
ports:
  - 8000

resources:
  gpu: 24GB
```

</div>

### Deploying as a service

If you'd like to deploy the model as an auto-scalable and secure endpoint,
use the [service](https://dstack.ai/docs/services) configuration. You can find it at [`examples/deployment/vllm/serve.dstack.yml` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/deployment/vllm/serve.dstack.yml)

### Running a configuration

To run a configuration, use the [`dstack apply`](https://dstack.ai/docs/reference/cli/index.md#dstack-apply) command. 

<div class="termy">

```shell
$ dstack apply -f examples/deployment/vllm/serve-task.dstack.yml

 #  BACKEND  REGION         INSTANCE         RESOURCES   SPOT  PRICE     
 1  cudo     ca-montreal-1  intel-broadwell  2xCPU, 8GB,  no   $0.0276   
 2  cudo     ca-montreal-2  intel-broadwell  2xCPU, 8GB,  no   $0.0286   
 3  cudo     fi-tampere-1   intel-broadwell  2xCPU, 8GB,  no   $0.0383  

Submit a new run? [y/n]: y

Provisioning...
---> 100%
```
</div>

## Source code

The source-code of this example can be found in 
[`examples/deployment/vllm` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/deployment/vllm).

## What's next?

1. Check [dev environments](https://dstack.ai/docs/dev-environments), [tasks](https://dstack.ai/docs/tasks), 
   [services](https://dstack.ai/docs/services), and [protips](https://dstack.ai/docs/protips).
2. Browse [Deployment on AMD :material-arrow-top-right-thin:{ .external }](https://dstack.ai/examples/accelerators/amd/) and
   [Deployment on TPU :material-arrow-top-right-thin:{ .external }](https://dstack.ai/examples/accelerators/tpu/).
   