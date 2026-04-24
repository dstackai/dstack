---
title: vLLM
description: Deploying Qwen3.6-27B using vLLM on NVIDIA and AMD GPUs
---

# vLLM

This example shows how to deploy `Qwen/Qwen3.6-27B` using
[vLLM](https://docs.vllm.ai/en/latest/) and `dstack`.

## Apply a configuration

Here's an example of a service that deploys
`Qwen/Qwen3.6-27B` using vLLM.

=== "NVIDIA"

    <div editor-title="qwen36.dstack.yml">

    ```yaml
    type: service
    name: qwen36

    image: vllm/vllm-openai:v0.19.1

    commands:
      - |
        vllm serve Qwen/Qwen3.6-27B \
          --host 0.0.0.0 \
          --port 8000 \
          --tensor-parallel-size $DSTACK_GPUS_NUM \
          --max-model-len 262144 \
          --reasoning-parser qwen3

    port: 8000
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

    image: vllm/vllm-openai-rocm:v0.19.1

    commands:
      - |
        vllm serve Qwen/Qwen3.6-27B \
          --host 0.0.0.0 \
          --port 8000 \
          --tensor-parallel-size $DSTACK_GPUS_NUM \
          --max-model-len 262144 \
          --reasoning-parser qwen3

    port: 8000
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

Qwen3.6-27B is a multimodal model. For text-only workloads, add
`--language-model-only` to free more memory for the KV cache. To enable tool
calling, add `--enable-auto-tool-choice --tool-call-parser qwen3_coder`.

Save one of the configurations above as `qwen36.dstack.yml`, then use the
[`dstack apply`](https://dstack.ai/docs/reference/cli/dstack/apply.md) command.

<div class="termy">

```shell
$ dstack apply -f qwen36.dstack.yml
```

</div>

If no gateway is created, the service endpoint will be available at `<dstack server URL>/proxy/services/<project name>/<run name>/`.

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
          "content": "A bat and a ball cost $1.10 total. The bat costs $1.00 more than the ball. How much does the ball cost?"
        }
      ],
      "max_tokens": 1024
    }'
```

</div>

> If a [gateway](https://dstack.ai/docs/concepts/gateways/) is configured (e.g. to enable auto-scaling, HTTPS, rate limits, etc.), the service endpoint will be available at `https://qwen36.<gateway domain>/`.

## What's next?

1. Read about [services](https://dstack.ai/docs/concepts/services) and [gateways](https://dstack.ai/docs/concepts/gateways)
2. Browse the [Qwen 3.5 & 3.6 vLLM recipe](https://docs.vllm.ai/projects/recipes/en/latest/Qwen/Qwen3.5.html) and the [SGLang](https://dstack.ai/examples/inference/sglang/) example
