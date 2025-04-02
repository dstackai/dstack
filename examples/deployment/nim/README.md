---
title: NVIDIA NIM
description: "This example shows how to deploy DeepSeek-R1-Distill-Llama-8B to any cloud or on-premises environment using NVIDIA NIM and dstack."
---

# NVIDIA NIM 

This example shows how to deploy DeepSeek-R1-Distill-Llama-8B using [NVIDIA NIM :material-arrow-top-right-thin:{ .external }](https://docs.nvidia.com/nim/large-language-models/latest/getting-started.html){:target="_blank"} and `dstack`.

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

Here's an example of a service that deploys DeepSeek-R1-Distill-Llama-8B using NIM.

<div editor-title="examples/deployment/nim/.dstack.yml">

```yaml
type: service
name: serve-distill-deepseek

image: nvcr.io/nim/deepseek-ai/deepseek-r1-distill-llama-8b
env:
  - NGC_API_KEY
  - NIM_MAX_MODEL_LEN=4096
registry_auth:
  username: $oauthtoken
  password: ${{ env.NGC_API_KEY }}
port: 8000
# Register the model
model: deepseek-ai/deepseek-r1-distill-llama-8b

# Uncomment to leverage spot instances
#spot_policy: auto

# Cache downloaded models
volumes:
  - instance_path: /root/.cache/nim
    path: /opt/nim/.cache
    optional: true

resources:
  gpu: A100:40GB
  # Uncomment if using multiple GPUs
  #shm_size: 16GB
```
</div>

### Running a configuration

To run a configuration, use the [`dstack apply`](https://dstack.ai/docs/reference/cli/dstack/apply.md) command. 

<div class="termy">

```shell
$ NGC_API_KEY=...
$ dstack apply -f examples/deployment/nim/.dstack.yml

 #  BACKEND  REGION    RESOURCES                  SPOT  PRICE       
 1  vultr    ewr       6xCPU, 60GB, 1xA100 (40GB) no    $1.199   
 2  vultr    ewr       6xCPU, 60GB, 1xA100 (40GB) no    $1.199  
 3  vultr    nrt       6xCPU, 60GB, 1xA100 (40GB) no    $1.199 

Submit the run serve-distill-deepseek? [y/n]: y

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

## What's next?

1. Check [services](https://dstack.ai/docs/services)
2. Browse the [DeepSeek AI NIM](https://build.nvidia.com/deepseek-ai)
