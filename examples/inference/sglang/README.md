---
title: SGLang
description: Deploying Qwen3.5-397B-A17B-FP8 using SGLang on NVIDIA and AMD GPUs
---

# SGLang

This example shows how to deploy `Qwen/Qwen3.5-397B-A17B-FP8` using
[SGLang](https://github.com/sgl-project/sglang) and `dstack`.

## Apply a configuration

Here's an example of a service that deploys
`Qwen/Qwen3.5-397B-A17B-FP8` using SGLang.

=== "NVIDIA"

    <div editor-title="qwen397.dstack.yml">

    ```yaml
    type: service
    name: qwen397

    image: lmsysorg/sglang:v0.5.10.post1

    commands:
      - |
        sglang serve \
          --model-path Qwen/Qwen3.5-397B-A17B-FP8 \
          --port 30000 \
          --tp $DSTACK_GPUS_NUM \
          --reasoning-parser qwen3 \
          --tool-call-parser qwen3_coder \
          --enable-flashinfer-allreduce-fusion \
          --mem-fraction-static 0.8

    port: 30000
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

=== "AMD"

    <div editor-title="qwen397.dstack.yml">

    ```yaml
    type: service
    name: qwen397

    image: lmsysorg/sglang:v0.5.10.post1-rocm720-mi30x

    env:
      - HIP_FORCE_DEV_KERNARG=1
      - SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN=1
      - SGLANG_DISABLE_CUDNN_CHECK=1
      - SGLANG_INT4_WEIGHT=0
      - SGLANG_MOE_PADDING=1
      - SGLANG_ROCM_DISABLE_LINEARQUANT=0
      - SGLANG_ROCM_FUSED_DECODE_MLA=1
      - SGLANG_SET_CPU_AFFINITY=1
      - SGLANG_USE_AITER=1
      - SGLANG_USE_ROCM700A=1

    commands:
      - |
        sglang serve \
          --model-path Qwen/Qwen3.5-397B-A17B-FP8 \
          --tp $DSTACK_GPUS_NUM \
          --reasoning-parser qwen3 \
          --tool-call-parser qwen3_coder \
          --mem-fraction-static 0.8 \
          --context-length 262144 \
          --attention-backend triton \
          --disable-cuda-graph \
          --fp8-gemm-backend aiter \
          --port 30000

    port: 30000
    model: Qwen/Qwen3.5-397B-A17B-FP8

    volumes:
      - instance_path: /root/.cache
        path: /root/.cache
        optional: true

    resources:
      cpu: x86:52..
      memory: 700GB..
      shm_size: 16GB
      disk: 600GB..
      gpu: MI300X:192GB:4
    ```
    </div>

The AMD example uses the exact validated MI300X configuration for this model,
including the ROCm/AITER settings required for stable FP8 serving.

Save one of the configurations above as `qwen397.dstack.yml`, then use the
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
          "content": "A bat and a ball cost $1.10 total. The bat costs $1.00 more than the ball. How much does the ball cost? Answer with just the dollar amount."
        }
      ],
      "chat_template_kwargs": {"enable_thinking": true},
      "separate_reasoning": true,
      "max_tokens": 1024
    }'
```
</div>

> If a [gateway](https://dstack.ai/docs/concepts/gateways/) is configured (e.g. to enable auto-scaling, HTTPS, rate limits, etc.), the service endpoint will be available at `https://qwen397.<gateway domain>/`.

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
2. Browse the [Qwen 3.5 SGLang cookbook](https://cookbook.sglang.io/autoregressive/Qwen/Qwen3.5) and the [SGLang server arguments reference](https://docs.sglang.ai/advanced_features/server_arguments.html)
