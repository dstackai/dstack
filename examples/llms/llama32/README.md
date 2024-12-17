# Llama 3.2

This example walks you through how to deploy Llama 3.2 vision model with `dstack` using `vLLM`.

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

Here's an example of a service that deploys Llama 3.2 11B using vLLM.

<div editor-title="examples/llms/llama32/vllm/.dstack.yml"> 

```yaml
type: service
name: llama32

image: vllm/vllm-openai:latest
env:
  - HF_TOKEN
  - MODEL_ID=meta-llama/Llama-3.2-11B-Vision-Instruct
  - MAX_MODEL_LEN=4096
  - MAX_NUM_SEQS=8
commands:
  - vllm serve $MODEL_ID
    --max-model-len $MAX_MODEL_LEN
    --max-num-seqs $MAX_NUM_SEQS
    --enforce-eager
    --disable-log-requests
    --limit-mm-per-prompt "image=1"
    --tensor-parallel-size $DSTACK_GPUS_NUM
port: 8000
# Register the model
model: meta-llama/Llama-3.2-11B-Vision-Instruct

# Uncomment to cache downloaded models
#volumes:
#  - /root/.cache/huggingface/hub:/root/.cache/huggingface/hub

resources:
  gpu: 40GB..48GB
```
</div>

[//]: # (TODO: Comment on MAX_MODEL_LEN and MAX_NUM_SEQS)

### Memory requirements

Below are the approximate memory requirements for loading the model. 
This excludes memory for the model context and CUDA kernel reservations.

| Model size | FP16  |
|------------|-------|
| **11B**    | 40GB  |
| **90B**    | 180GB |

[//]: # (TODO: Quantization mention)

### Running a configuration

To run a configuration, use the [`dstack apply`](https://dstack.ai/docs/reference/cli/dstack/apply.md) command.

<div class="termy">

```shell
$ HF_TOKEN=...
$ dstack apply -f examples/llms/llama32/vllm/.dstack.yml

 #  BACKEND  REGION     RESOURCES                    SPOT  PRICE   
 1  runpod   CA-MTL-1   9xCPU, 50GB, 1xA40 (48GB)    yes   $0.24   
 2  runpod   EU-SE-1    9xCPU, 50GB, 1xA40 (48GB)    yes   $0.24   
 3  runpod   EU-SE-1    9xCPU, 50GB, 1xA6000 (48GB)  yes   $0.25   

 
Submit the run llama32? [y/n]: y

Provisioning...
---> 100%
```

</div>

Once the service is up, it will be available via the service endpoint
at `<dstack server URL>/proxy/services/<project name>/<run name>/`.

<div class="termy">

```shell
$ curl http://127.0.0.1:3000/proxy/services/main/llama32/v1/chat/completions \
    -H 'Content-Type: application/json' \
    -H 'Authorization: Bearer token' \
    --data '{
        "model": "meta-llama/Llama-3.2-11B-Vision-Instruct",
        "messages": [
        {
            "role": "user",
            "content": [
                {"type" : "text", "text": "Describe the image."},
                {"type": "image_url", "image_url": {"url": "https://upload.wikimedia.org/wikipedia/commons/e/ea/Bento_at_Hanabishi%2C_Koyasan.jpg"}}
            ]
        }],
        "max_tokens": 2048
    }'
```

</div>

When a [gateway](https://dstack.ai/docs/concepts/gateways.md) is configured, the service endpoint 
is available at `https://<run name>.<gateway domain>/`.

[//]: # (TODO: https://github.com/dstackai/dstack/issues/1777)

## Source code

The source-code of this example can be found in 
[`examples/llms/llama32` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/llms/llama32).

## What's next?

1. Check [dev environments](https://dstack.ai/docs/dev-environments), [tasks](https://dstack.ai/docs/tasks), 
   [services](https://dstack.ai/docs/services), and [protips](https://dstack.ai/docs/protips).
2. Browse [Llama 3.2 on HuggingFace :material-arrow-top-right-thin:{ .external }](https://huggingface.co/collections/meta-llama/llama-32-66f448ffc8c32f949b04c8cf)
   and [LLama 3.2 on vLLM :material-arrow-top-right-thin:{ .external }](https://docs.vllm.ai/en/latest/models/supported_models.html#multimodal-language-models).
