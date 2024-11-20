# Text Generation Inference

This example shows how to deploy Llama 3.1 8B with `dstack` using [TGI :material-arrow-top-right-thin:{ .external }](https://huggingface.co/docs/text-generation-inference/en/index){:target="_blank"}.

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

Here's an example of a service that deploys Llama 3.1 8B using TGI.

<div editor-title="examples/deployment/tgi/.dstack.yml">

```yaml
type: service
name: llama31

image: ghcr.io/huggingface/text-generation-inference:latest
env:
  - HF_TOKEN
  - MODEL_ID=meta-llama/Meta-Llama-3.1-8B-Instruct
  - MAX_INPUT_LENGTH=4000
  - MAX_TOTAL_TOKENS=4096
commands:
  - NUM_SHARD=$DSTACK_GPUS_NUM text-generation-launcher
port: 80
# Register the model
model: meta-llama/Meta-Llama-3.1-8B-Instruct

# Uncomment to leverage spot instances
#spot_policy: auto

# Uncomment to cache downloaded models  
#volumes:
#  - /data:/data

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
$ HF_TOKEN=...
$ dstack apply -f examples/deployment/tgi/.dstack.yml

 #  BACKEND     REGION        RESOURCES                      SPOT  PRICE    
 1  tensordock  unitedstates  2xCPU, 10GB, 1xRTX3090 (24GB)  no    $0.231   
 2  tensordock  unitedstates  2xCPU, 10GB, 1xRTX3090 (24GB)  no    $0.242   
 3  tensordock  india         2xCPU, 38GB, 1xA5000 (24GB)    no    $0.283  

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
[`examples/deployment/tgi` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/deployment/tgi).

## What's next?

1. Check [services](https://dstack.ai/docs/services)
2. Browse the [Llama 3.1](https://dstack.ai/examples/llms/llama31/), [vLLM](https://dstack.ai/examples/deployment/vllm/),
   and [NIM](https://dstack.ai/examples/deployment/nim/) examples
3. See also [AMD](https://dstack.ai/examples/accelerators/amd/) and
   [TPU](https://dstack.ai/examples/accelerators/tpu/)
