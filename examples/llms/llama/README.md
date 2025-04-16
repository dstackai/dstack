# Llama

This example walks you through how to deploy Llama 4 Scout model with `dstack`.

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

### AMD
Here's an example of a service that deploys 
[`Llama-4-Scout-17B-16E-Instruct` :material-arrow-top-right-thin:{ .external }](https://huggingface.co/meta-llama/Llama-4-Scout-17B-16E-Instruct){:target="_blank"} 
using [vLLM :material-arrow-top-right-thin:{ .external }](https://github.com/vllm-project/vllm){:target="_blank"} 
with AMD `MI300X` GPUs.

<div editor-title="examples/llms/llama/vllm/amd/.dstack.yml">

```yaml
type: service
name: llama4-scout

image: rocm/vllm-dev:llama4-20250407
env:
  - HF_TOKEN
  - MODEL_ID=meta-llama/Llama-4-Scout-17B-16E-Instruct
  - VLLM_WORKER_MULTIPROC_METHOD=spawn
  - VLLM_USE_MODELSCOPE=False
  - VLLM_USE_TRITON_FLASH_ATTN=0 
  - MAX_MODEL_LEN=256000

commands:
   - |
     vllm serve $MODEL_ID \
       --tensor-parallel-size $DSTACK_GPUS_NUM \
       --max-model-len $MAX_MODEL_LEN \
       --kv-cache-dtype fp8 \
       --max-num-seqs 64 \
       --override-generation-config='{"attn_temperature_tuning": true}'

   
port: 8000
# Register the model
model: meta-llama/Llama-4-Scout-17B-16E-Instruct

resources:
  gpu: Mi300x:2
  disk: 500GB..
```
</div>

### NVIDIA
Here's an example of a service that deploys 
[`Llama-4-Scout-17B-16E-Instruct` :material-arrow-top-right-thin:{ .external }](https://huggingface.co/meta-llama/Llama-4-Scout-17B-16E-Instruct){:target="_blank"} 
using [SGLang :material-arrow-top-right-thin:{ .external }](https://github.com/sgl-project/sglang){:target="_blank"} and [vLLM :material-arrow-top-right-thin:{ .external }](https://github.com/vllm-project/vllm){:target="_blank"} 
with NVIDIA `H200` GPUs.

=== "SGLang"

    <div editor-title="examples/llms/llama/sglang/nvidia/.dstack.yml">

    ```yaml
    type: service
    name: llama4-scout

    image: lmsysorg/sglang
    env:
      - HF_TOKEN
      - MODEL_ID=meta-llama/Llama-4-Scout-17B-16E-Instruct
      - CONTEXT_LEN=256000
    commands:
       - python3 -m sglang.launch_server
           --model-path $MODEL_ID
           --tp $DSTACK_GPUS_NUM
           --context-length $CONTEXT_LEN
           --kv-cache-dtype fp8_e5m2
           --port 8000

    port: 8000
    ## Register the model
    model: meta-llama/Llama-4-Scout-17B-16E-Instruct

    resources:
      gpu: H200:2
      disk: 500GB..
    ```
    </div>

=== "vLLM"
    
    <div editor-title="examples/llms/llama/vllm/nvidia/.dstack.yml">

    ```yaml
    type: service
    name: llama4-scout

    image: vllm/vllm-openai
    env:
      - HF_TOKEN
      - MODEL_ID=meta-llama/Llama-4-Scout-17B-16E-Instruct
      - VLLM_DISABLE_COMPILE_CACHE=1
      - MAX_MODEL_LEN=256000
    commands:
       - |
         vllm serve $MODEL_ID \
           --tensor-parallel-size $DSTACK_GPUS_NUM \
           --max-model-len $MAX_MODEL_LEN \
           --kv-cache-dtype fp8 \
           --override-generation-config='{"attn_temperature_tuning": true}'

    port: 8000
    # Register the model
    model: meta-llama/Llama-4-Scout-17B-16E-Instruct

    resources:
      gpu: H200:2
      disk: 500GB..
    ```
    </div>

!!! info "NOTE:"
    With vLLM, add `--override-generation-config='{"attn_temperature_tuning": true}'` to 
    improve accuracy for [contexts longer than 32K tokens :material-arrow-top-right-thin:{ .external }](https://blog.vllm.ai/2025/04/05/llama4.html){:target="_blank"}.

### Memory requirements

Below are the approximate memory requirements for loading the model. 
This excludes memory for the model context and CUDA kernel reservations.

| Model         | Size     | FP16   | FP8    | INT4   |
|---------------|----------|--------|--------|--------|
| `Behemoth`    | **2T**   | 4TB    | 2TB    | 1TB    |
| `Maverick`    | **400B** | 800GB  | 200GB  | 100GB  |
| `Scout`       | **109B** | 218GB  | 109GB  | 54.5GB |


### Running a configuration

To run a configuration, use the [`dstack apply`](https://dstack.ai/docs/reference/cli/dstack/apply.md) command.

<div class="termy">

```shell
$ HF_TOKEN=...
$ dstack apply -f examples/llms/llama/sglang/nvidia/.dstack.yml

 #  BACKEND  REGION     RESOURCES                      SPOT PRICE   
 1  vastai   is-iceland 48xCPU, 128GB, 2xH200 (140GB)  no   $7.87   
 2  runpod   EU-SE-1    40xCPU, 128GB, 2xH200 (140GB)  no   $7.98  

 
Submit the run llama4-scout? [y/n]: y

Provisioning...
---> 100%
```

</div>

Once the service is up, it will be available via the service endpoint
at `<dstack server URL>/proxy/services/<project name>/<run name>/`.

<div class="termy">

```shell
curl http://127.0.0.1:3000/proxy/models/main/chat/completions \
    -X POST \
    -H 'Authorization: Bearer &lt;dstack token&gt;' \
    -H 'Content-Type: application/json' \
    -d '{
      "model": "meta-llama/Llama-4-Scout-17B-16E-Instruct",
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
      "stream": true,
      "max_tokens": 512
    }'
```

</div>

When a [gateway](https://dstack.ai/docs/concepts/gateways.md) is configured, the service endpoint 
is available at `https://<run name>.<gateway domain>/`.

[//]: # (TODO: https://github.com/dstackai/dstack/issues/1777)

## Source code

The source-code of this example can be found in 
[`examples/llms/llama` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/llms/llama).

## What's next?

1. Check [dev environments](https://dstack.ai/docs/dev-environments), [tasks](https://dstack.ai/docs/tasks), 
   [services](https://dstack.ai/docs/services), and [protips](https://dstack.ai/docs/protips).
2. Browse [Llama 4 with SGLang :material-arrow-top-right-thin:{ .external }](https://github.com/sgl-project/sglang/blob/main/docs/references/llama4.md), [Llama 4 with vLLM :material-arrow-top-right-thin:{ .external }](https://blog.vllm.ai/2025/04/05/llama4.html) and [Llama 4 with AMD :material-arrow-top-right-thin:{ .external }](https://rocm.blogs.amd.com/artificial-intelligence/llama4-day-0-support/README.html).
