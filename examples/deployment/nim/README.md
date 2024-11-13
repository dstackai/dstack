# NIM

This example shows how to deploy `Meta/LLama3-8b-instruct` with `dstack` using [NIM :material-arrow-top-right-thin:{ .external }](https://docs.nvidia.com/nim/large-language-models/latest/getting-started.html).

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
If you'd like to run Meta/Llama 3-8b for development purposes, consider using `dstack` [tasks](https://dstack.ai/docs/tasks/).

<div editor-title="examples/deployment/nim/task.dstack.yml">

```yaml
type: task

name: llama3-nim-task
image: nvcr.io/nim/meta/llama3-8b-instruct:latest

env:
  - NGC_API_KEY
registry_auth:
  username: $oauthtoken
  password: ${{ env.NGC_API_KEY }}

ports: 
  - 8000

spot_policy: auto

resources:
  gpu: 24GB

backends: ["aws", "azure", "cudo", "datacrunch", "gcp", "lambda", "oci", "tensordock"]
```
</div>
Note, Currently NIM is supported on every backend except RunPod and Vast.ai.

### Deploying as a service

If you'd like to deploy the model as an auto-scalable and secure endpoint,
use the [service](https://dstack.ai/docs/services) configuration. You can find it at [`examples/deployment/nim/service.dstack.yml` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/deployment/nim/service.dstack.yml)

### Running a configuration

To run a configuration, use the [`dstack apply`](https://dstack.ai/docs/reference/cli/index.md#dstack-apply) command. 

<div class="termy">

```shell
$ NGC_API_KEY=...

$ dstack apply -f examples/deployment/nim/task.dstack.yml

 #  BACKEND  REGION             RESOURCES                 SPOT  PRICE       
 1  gcp      asia-northeast3    4xCPU, 16GB, 1xL4 (24GB)  yes   $0.17   
 2  gcp      asia-east1         4xCPU, 16GB, 1xL4 (24GB)  yes   $0.21   
 3  gcp      asia-northeast3    8xCPU, 32GB, 1xL4 (24GB)  yes   $0.21 

Submit the run llama3-nim-task? [y/n]: y

Provisioning...
---> 100%
```
</div>


## Source code

The source-code of this example can be found in 
[`examples/deployment/nim` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/deployment/nim).

## What's next?

1. Check [dev environments](https://dstack.ai/docs/dev-environments), [tasks](https://dstack.ai/docs/tasks), 
   [services](https://dstack.ai/docs/services), and [protips](https://dstack.ai/docs/protips).
2. Browse [Available models in NGC Catalog :material-arrow-top-right-thin:{ .external }](https://catalog.ngc.nvidia.com/containers?filters=nvidia_nim%7CNVIDIA+NIM%7Cnimmcro_nvidia_nim&orderBy=scoreDESC&query=&page=&pageSize=).