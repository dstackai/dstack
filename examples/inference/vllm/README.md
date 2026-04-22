---
title: vLLM
description: Deploying Qwen3.5-397B-A17B-FP8 using vLLM on NVIDIA GPUs
---

# vLLM

This example shows how to deploy `Qwen/Qwen3.5-397B-A17B-FP8` using
[vLLM](https://docs.vllm.ai/en/latest/) and `dstack`.

## Apply a configuration

Here's an example of a service that deploys
`Qwen/Qwen3.5-397B-A17B-FP8` using vLLM.

=== "NVIDIA"

    <div editor-title="qwen397.dstack.yml">

    ```yaml
    type: service
    name: qwen397

    image: vllm/vllm-openai:v0.19.1

    commands:
      - |
        vllm serve Qwen/Qwen3.5-397B-A17B-FP8 \
          --port 8000 \
          --tensor-parallel-size $DSTACK_GPUS_NUM \
          --max-model-len 262144 \
          --reasoning-parser qwen3 \
          --language-model-only

    port: 8000
    model: Qwen/Qwen3.5-397B-A17B-FP8

    volumes:
      - instance_path: /root/.cache
        path: /root/.cache
        optional: true

    resources:
      cpu: x86:96..
      memory: 512GB..
      shm_size: 16GB
      disk: 500GB..
      gpu: H100:80GB:8
    ```

    </div>

The NVIDIA example serves `Qwen/Qwen3.5-397B-A17B-FP8` on `8x H100` GPUs using
vLLM with tensor parallelism enabled. It uses `--language-model-only` because
`Qwen/Qwen3.5-397B-A17B-FP8` is a text-only model.

Save the configuration above as `qwen397.dstack.yml`, then use the
[`dstack apply`](https://dstack.ai/docs/reference/cli/dstack/apply.md) command.

<div class="termy">

```shell
$ dstack apply -f qwen397.dstack.yml
```

</div>

If no gateway is created, the service endpoint will be available at `<dstack server URL>/proxy/services/<project name>/<run name>/`.

<div class="termy">

```shell
curl http://127.0.0.1:3000/proxy/services/main/qwen397/v1/chat/completions \
    -X POST \
    -H 'Authorization: Bearer &lt;dstack token&gt;' \
    -H 'Content-Type: application/json' \
    -d '{
      "model": "Qwen/Qwen3.5-397B-A17B-FP8",
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

> Qwen reasoning output depends on the backend. In `vLLM`, it is returned
> under `message.reasoning`.

> If a [gateway](https://dstack.ai/docs/concepts/gateways/) is configured (e.g. to enable auto-scaling, HTTPS, rate limits, etc.), the service endpoint will be available at `https://qwen397.<gateway domain>/`.

## What's next?

1. Read about [services](https://dstack.ai/docs/concepts/services) and [gateways](https://dstack.ai/docs/concepts/gateways)
2. Browse the [SGLang](https://dstack.ai/examples/inference/sglang/) and [NIM](https://dstack.ai/examples/inference/nim/) examples
