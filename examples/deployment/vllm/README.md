---
description: "This example shows how to deploy Llama 3.1 to any cloud or on-premises environment using vLLM and dstack."
---

# vLLM

This example shows how to deploy Llama 3.1 8B with `dstack` using [vLLM :material-arrow-top-right-thin:{ .external }](https://docs.vllm.ai/en/latest/){:target="_blank"}.

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

<div editor-title="examples/deployment/vllm/.dstack.yml">

```yaml
type: service
name: llama31

python: "3.11"
env:
  - HF_TOKEN
  - MODEL_ID=meta-llama/Meta-Llama-3.1-8B-Instruct
  - MAX_MODEL_LEN=4096
commands:
  - pip install vllm
  - vllm serve $MODEL_ID
    --max-model-len $MAX_MODEL_LEN
    --tensor-parallel-size $DSTACK_GPUS_NUM
port: 8000
# Register the model
model: meta-llama/Meta-Llama-3.1-8B-Instruct

# Uncomment to leverage spot instances
#spot_policy: auto

# Uncomment to cache downloaded models
#volumes:
#  - /root/.cache/huggingface/hub:/root/.cache/huggingface/hub

resources:
  gpu: 24GB
  # Uncomment if using multiple GPUs
  #shm_size: 24GB
```

</div>

### Running a configuration

To run a configuration, use the [`dstack apply`](https://dstack.ai/docs/reference/cli/dstack/apply.md) command. 

<div class="termy">

```shell
$ dstack apply -f examples/deployment/vllm/.dstack.yml

 #  BACKEND  REGION    RESOURCES                    SPOT  PRICE     
 1  runpod   CA-MTL-1  18xCPU, 100GB, A5000:24GB    yes   $0.12
 2  runpod   EU-SE-1   18xCPU, 100GB, A5000:24GB    yes   $0.12
 3  gcp      us-west4  27xCPU, 150GB, A5000:24GB:2  yes   $0.23

Submit a new run? [y/n]: y

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
      "model": "meta-llama/Meta-Llama-3.1-8B-Instruct",
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
[`examples/deployment/vllm` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/deployment/vllm).

## What's next?

1. Check [services](https://dstack.ai/docs/services)
2. Browse the [Llama 3.1](https://dstack.ai/examples/llms/llama31/), [TGI](https://dstack.ai/examples/deployment/tgi/)
   and [NIM](https://dstack.ai/examples/deployment/nim/) examples
3. See also [AMD](https://dstack.ai/examples/accelerators/amd/) and
   [TPU](https://dstack.ai/examples/accelerators/tpu/)
