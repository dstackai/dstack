---
title: Deploying LLMs with dstack using NIM
description: "This example shows how to deploy Llama 3.1 to any cloud or on-premises environment using NVIDIA NIM and dstack."
---

# NIM 

This example shows how to deploy LLama 3.1 using [NVIDIA NIM :material-arrow-top-right-thin:{ .external }](https://docs.nvidia.com/nim/large-language-models/latest/getting-started.html){:target="_blank"} and `dstack`.

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

Here's an example of a service that deploys Llama 3.1 8B using vLLM.

<div editor-title="examples/deployment/nim/.dstack.yml">

```yaml
type: service
name: llama31

image: nvcr.io/nim/meta/llama-3.1-8b-instruct:latest
env:
  - NGC_API_KEY
  - NIM_MAX_MODEL_LEN=4096
registry_auth:
  username: $oauthtoken
  password: ${{ env.NGC_API_KEY }}
port: 8000
# Register the model
model: meta/llama-3.1-8b-instruct

# Uncomment to leverage spot instances
#spot_policy: auto

# Cache downloaded models
volumes:
  - /root/.cache/nim:/opt/nim/.cache

resources:
  gpu: 24GB
  # Uncomment if using multiple GPUs
  #shm_size: 24GB
```
</div>

### Running a configuration

To run a configuration, use the [`dstack apply`](https://dstack.ai/docs/reference/cli/index.md#dstack-apply) command. 

<div class="termy">

```shell
$ NGC_API_KEY=...
$ dstack apply -f examples/deployment/nim/.dstack.yml

 #  BACKEND  REGION             RESOURCES                 SPOT  PRICE       
 1  gcp      asia-northeast3    4xCPU, 16GB, 1xL4 (24GB)  yes   $0.17   
 2  gcp      asia-east1         4xCPU, 16GB, 1xL4 (24GB)  yes   $0.21   
 3  gcp      asia-northeast3    8xCPU, 32GB, 1xL4 (24GB)  yes   $0.21 

Submit the run llama3-nim-task? [y/n]: y

Provisioning...
---> 100%
```
</div>

If no gateway is created, the model will be available via the OpenAI-compatible endpoint 
at `<dstack server URL>/proxy/models/<project name>/`.

<div class="termy">

```shell
$ curl http://127.0.0.1:3000/proxy/models/main/chat/completions \
    -X POST \
    -H 'Authorization: Bearer &lt;dstack token&gt;' \
    -H 'Content-Type: application/json' \
    -d '{
      "model": "meta/llama3-8b-instruct",
      "messages": [
        {
          "role": "system",
          "content": "You are a helpful assistant."
        },
        {
          "role": "user",
          "content": "What is Deep Learning?"
        }
      ],
      "max_tokens": 128
    }'
```

</div>

When a [gateway](https://dstack.ai/docs/concepts/gateways.md) is configured, the OpenAI-compatible endpoint 
is available at `https://gateway.<gateway domain>/`.

## Source code

The source-code of this example can be found in 
[`examples/deployment/nim` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/deployment/nim){:target="_blank"}.

??? warning "Limitations"
    NIM isn't working yet with `runpod` and `vastai` backends. 
    Track the [issue :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/issues/1535){:target="_blank"} for progress.

## What's next?

1. Check [services](https://dstack.ai/docs/services)
2. Browse the [Llama 3.1](https://dstack.ai/examples/llms/llama31/), [TGI](https://dstack.ai/examples/deployment/tgi/), 
   and [vLLM](https://dstack.ai/examples/deployment/vllm/) examples
3. See also [AMD](https://dstack.ai/examples/accelerators/amd/) and
   [TPU](https://dstack.ai/examples/accelerators/tpu/)
