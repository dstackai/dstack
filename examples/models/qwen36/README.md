---
title: Qwen 3.6
description: Deploying Qwen3.6-27B using SGLang on NVIDIA and AMD GPUs
---

# Qwen 3.6

This example shows how to deploy `Qwen/Qwen3.6-27B` as a
[service](https://dstack.ai/docs/services) using
[SGLang](https://github.com/sgl-project/sglang) and `dstack`.

## Apply a configuration

Save one of the following configurations as `qwen36.dstack.yml`.

=== "NVIDIA"

    <div editor-title="qwen36.dstack.yml">

    ```yaml
    type: service
    name: qwen36

    image: lmsysorg/sglang:v0.5.10.post1

    commands:
      - |
        sglang serve \
          --model-path Qwen/Qwen3.6-27B \
          --host 0.0.0.0 \
          --port 30000 \
          --tp $DSTACK_GPUS_NUM \
          --reasoning-parser qwen3 \
          --mem-fraction-static 0.8 \
          --context-length 262144

    port: 30000
    model: Qwen/Qwen3.6-27B

    volumes:
      - instance_path: /root/.cache
        path: /root/.cache
        optional: true

    resources:
      shm_size: 16GB
      gpu: H100:4
    ```

    </div>

=== "AMD"

    <div editor-title="qwen36.dstack.yml">

    ```yaml
    type: service
    name: qwen36

    image: lmsysorg/sglang:v0.5.10-rocm720-mi30x

    commands:
      - |
        sglang serve \
          --model-path Qwen/Qwen3.6-27B \
          --host 0.0.0.0 \
          --port 30000 \
          --tp $DSTACK_GPUS_NUM \
          --reasoning-parser qwen3 \
          --mem-fraction-static 0.8 \
          --context-length 262144

    port: 30000
    model: Qwen/Qwen3.6-27B

    volumes:
      - instance_path: /root/.cache
        path: /root/.cache
        optional: true

    resources:
      cpu: 52..
      memory: 896GB..
      shm_size: 16GB
      disk: 450GB..
      gpu: MI300X:4
    ```

    </div>

The NVIDIA and AMD configurations above use pinned SGLang images and the same
straightforward 4-GPU layout used across the Qwen 3.6 docs and examples.

Apply the configuration with
[`dstack apply`](https://dstack.ai/docs/reference/cli/dstack/apply.md).

<div class="termy">

```shell
$ dstack apply -f qwen36.dstack.yml
```

</div>

If no gateway is created, the service endpoint will be available at
`<dstack server URL>/proxy/services/<project name>/<run name>/`.

<div class="termy">

```shell
curl http://127.0.0.1:3000/proxy/services/main/qwen36/v1/chat/completions \
    -X POST \
    -H 'Authorization: Bearer &lt;dstack token&gt;' \
    -H 'Content-Type: application/json' \
    -d '{
      "model": "Qwen/Qwen3.6-27B",
      "messages": [
        {
          "role": "user",
          "content": "A bat and a ball cost $1.10 total. The bat costs $1.00 more than the ball. How much does the ball cost? Answer with just the dollar amount."
        }
      ],
      "max_tokens": 1024
    }'
```

</div>

## Thinking mode

Qwen3.6 uses thinking mode by default. With SGLang, the reasoning stream is
returned separately as `reasoning_content`.

To disable thinking, pass `chat_template_kwargs` in the request body.

<div class="termy">

```shell
curl http://127.0.0.1:3000/proxy/services/main/qwen36/v1/chat/completions \
    -X POST \
    -H 'Authorization: Bearer &lt;dstack token&gt;' \
    -H 'Content-Type: application/json' \
    -d '{
      "model": "Qwen/Qwen3.6-27B",
      "messages": [
        {
          "role": "user",
          "content": "Summarize the benefits of container images in one sentence."
        }
      ],
      "max_tokens": 256,
      "chat_template_kwargs": {
        "enable_thinking": false
      }
    }'
```

</div>

## What's next?

1. Read the [Qwen/Qwen3.6-27B model card](https://huggingface.co/Qwen/Qwen3.6-27B)
2. Read the [Qwen 3.6 SGLang cookbook](https://docs.sglang.io/cookbook/autoregressive/Qwen/Qwen3.6)
3. Read the [Qwen 3.5 & 3.6 vLLM recipe](https://docs.vllm.ai/projects/recipes/en/latest/Qwen/Qwen3.5.html)
4. Browse the dedicated [SGLang](https://dstack.ai/examples/inference/sglang/)
   and [vLLM](https://dstack.ai/examples/inference/vllm/) examples
5. Check the [AMD](https://dstack.ai/examples/accelerators/amd/) example for
   more AMD deployment and training configurations
6. Run [NCCL/RCCL tests](https://dstack.ai/examples/clusters/nccl-rccl-tests/)
   if you're validating multi-node cluster networking
