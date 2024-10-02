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

### Running as a task

If you'd like to run Llama 3.2 vision model for development purposes, consider using `dstack` tasks.

<div editor-title="examples/llms/llama32/vllm/task.dstack.yml"> 

```yaml
type: task
name: llama32-task-vllm

# If `image` is not specified, dstack uses its default image
python: "3.10"

# Required environment variables
env:
  - HUGGING_FACE_HUB_TOKEN
  - MODEL_ID=meta-llama/Llama-3.2-11B-Vision-Instruct
  - MAX_MODEL_LEN=13488
  - MAX_NUM_SEQS=40

commands:
  - pip install vllm
  - vllm serve $MODEL_ID
    --tensor-parallel-size $DSTACK_GPUS_NUM
    --max-model-len $MAX_MODEL_LEN
    --max-num-seqs $MAX_NUM_SEQS
    --enforce-eager
    --disable-log-requests
    --limit-mm-per-prompt "image=1"
# Expose the vllm server port
ports:
  - 8000
ide: vscode
# Use either spot or on-demand instances
spot_policy: auto
# Uncomment to ensure it doesn't create a new fleet
#creation_policy: reuse

resources:
  # Required resources
  gpu: 48GB
```
</div>
Note, maximum size of vLLM’s `KV cache` is 13488, consequently we must set `MAX_MODEL_LEN` to 13488. `MAX_NUM_SEQS` greater than 40 results in an out of memory error.

### Deploying as a service

If you'd like to deploy Llama 3.2 vision model as public auto-scalable and secure endpoint,
consider using `dstack` [services](https://dstack.ai/docs/services).

### Memory requirements

Below are the approximate memory requirements for loading the model. 
This excludes memory for the model context and CUDA kernel reservations.

| Model size | FP16  |
|------------|-------|
| **11B**    | 40GB  |
| **90B**    | 180GB |



### Running a configuration

To run a configuration, use the [`dstack apply`](https://dstack.ai/docs/reference/cli/index.md#dstack-apply) command.

<div class="termy">

```shell
$ HUGGING_FACE_HUB_TOKEN=...

$ dstack apply -f examples/llms/llama32/vllm/task.dstack.yml

 #  BACKEND  REGION     RESOURCES                    SPOT  PRICE   
 1  runpod   CA-MTL-1   9xCPU, 50GB, 1xA40 (48GB)    yes   $0.24   
 2  runpod   EU-SE-1    9xCPU, 50GB, 1xA40 (48GB)    yes   $0.24   
 3  runpod   EU-SE-1    9xCPU, 50GB, 1xA6000 (48GB)  yes   $0.25   

 
Submit the run llama32-task-vllm? [y/n]: y

Provisioning...
---> 100%
```

</div>

If you run a task, `dstack apply` automatically forwards the remote ports to `localhost` for convenient access.

<div class="termy">

```shell
$ curl http://localhost:8000/v1/chat/completions \
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

## Source code

The source-code of this example can be found in 
[`examples/llms/llama32` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/llms/llama32).

## What's next?

1. Check [dev environments](https://dstack.ai/docs/dev-environments), [tasks](https://dstack.ai/docs/tasks), 
   [services](https://dstack.ai/docs/services), and [protips](https://dstack.ai/docs/protips).
2. Browse [Llama 3.2 on HuggingFace :material-arrow-top-right-thin:{ .external }](https://huggingface.co/collections/meta-llama/llama-32-66f448ffc8c32f949b04c8cf)
   and [LLama 3.2 on vLLM :material-arrow-top-right-thin:{ .external }](https://docs.vllm.ai/en/latest/models/supported_models.html#multimodal-language-models).
