---
title: SGLang
description: Deploying Qwen3.6-27B using SGLang on NVIDIA and AMD GPUs
---

# SGLang

This example shows how to deploy `Qwen/Qwen3.6-27B` using
[SGLang](https://github.com/sgl-project/sglang) and `dstack`.

## Apply a configuration

Here's an example of a service that deploys
`Qwen/Qwen3.6-27B` using SGLang.

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

The AMD example keeps the deployment close to the upstream Qwen and SGLang
guidance: a pinned ROCm image, tensor parallelism across all four GPUs, and the
standard `qwen3` reasoning parser without extra ROCm-specific tuning flags.
The first startup on MI300X can take longer while SGLang compiles ROCm kernels.

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
          "content": "A bat and a ball cost $1.10 total. The bat costs $1.00 more than the ball. How much does the ball cost? Answer with just the dollar amount."
        }
      ],
      "separate_reasoning": true,
      "max_tokens": 1024
    }'
```
</div>

Qwen3.6 uses thinking mode by default. To disable thinking, pass
`"chat_template_kwargs": {"enable_thinking": false}` in the request body. To
enable tool calling, add `--tool-call-parser qwen3_coder` to the serve command.

> If a [gateway](https://dstack.ai/docs/concepts/gateways/) is configured (e.g. to enable auto-scaling, HTTPS, rate limits, etc.), the service endpoint will be available at `https://qwen36.<gateway domain>/`.

## Configuration options

### PD disaggregation

To run SGLang with [PD disaggregation](https://docs.sglang.io/advanced_features/pd_disaggregation.html), use replicas groups: one for a router (for example, [SGLang Model Gateway](https://docs.sglang.io/advanced_features/sgl_model_gateway.html)), one for prefill workers, and one for decode workers.

=== "NVIDIA"

    <div editor-title="pd.dstack.yml">

    ```yaml
    type: service
    name: prefill-decode
    image: lmsysorg/sglang:v0.5.10.post1

    env:
      - HF_TOKEN
      - MODEL_ID=zai-org/GLM-4.5-Air-FP8

    replicas:
      - count: 1
        # For now replica group with router must have count: 1
        commands:
          - pip install sglang_router
          - |
            python -m sglang_router.launch_router \
              --host 0.0.0.0 \
              --port 8000 \
              --pd-disaggregation \
              --prefill-policy cache_aware
        router:
          type: sglang
        resources:
          cpu: 4

      - count: 1..4
        scaling:
          metric: rps
          target: 3
        commands:
          - |
            python -m sglang.launch_server \
              --model-path $MODEL_ID \
              --disaggregation-mode prefill \
              --disaggregation-transfer-backend nixl \
              --host 0.0.0.0 \
              --port 8000 \
              --disaggregation-bootstrap-port 8998
        resources:
          gpu: H200

      - count: 1..8
        scaling:
          metric: rps
          target: 2
        commands:
          - |
            python -m sglang.launch_server \
              --model-path $MODEL_ID \
              --disaggregation-mode decode \
              --disaggregation-transfer-backend nixl \
              --host 0.0.0.0 \
              --port 8000
        resources:
          gpu: H200

    port: 8000
    model: zai-org/GLM-4.5-Air-FP8

    # Custom probe is required for PD disaggregation.
    probes:
      - type: http
        url: /health
        interval: 15s
    ```

    </div>

Currently, auto-scaling only supports `rps` as the metric. TTFT and ITL metrics are coming soon.

!!! info "Cluster"
    PD disaggregation requires the service to run in a fleet with `placement` set to `cluster`, because the replicas require an interconnect between instances.

    While the prefill and decode replicas run on GPUs, the router replica requires a CPU instance in the same cluster.

## What's next?

1. Read about [services](https://dstack.ai/docs/concepts/services) and [gateways](https://dstack.ai/docs/concepts/gateways)
2. Browse the [Qwen 3.6 SGLang cookbook](https://docs.sglang.io/cookbook/autoregressive/Qwen/Qwen3.6) and the [SGLang server arguments reference](https://docs.sglang.ai/advanced_features/server_arguments.html)
