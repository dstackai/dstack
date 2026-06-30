---
title: SGLang
description: Deploying Qwen3.6-27B using SGLang on NVIDIA and AMD GPUs
---

# SGLang

This example shows how to deploy `Qwen/Qwen3.6-27B` using
[SGLang](https://github.com/sgl-project/sglang) and `dstack`.

> For a `DeepSeek-V4-Pro` deployment on `B200:8`, see the
[DeepSeek V4](../models/deepseek-v4.md) model page.

## Apply a configuration

Here's an example of a service that deploys
`Qwen/Qwen3.6-27B` using SGLang.

=== "NVIDIA"

    <div editor-title="service.dstack.yml">

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

    <div editor-title="service.dstack.yml">

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

Save one of the configurations above as `service.dstack.yml`, then use the
[`dstack apply`](../../reference/cli/dstack/apply.md) command.

<div class="termy">

```shell
$ dstack apply -f service.dstack.yml
```

</div>

If no gateway is created, the service endpoint will be available at `<dstack server URL>/proxy/services/<project name>/<run name>/`.

<div class="termy">

```shell
curl http://127.0.0.1:3000/proxy/services/main/qwen36/v1/chat/completions \
    -X POST \
    -H 'Authorization: Bearer &lt;user token&gt;' \
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

> If a [gateway](../../concepts/gateways.md) is configured (e.g. to enable auto-scaling, HTTPS, rate limits, etc.), the service endpoint will be available at `https://qwen36.<gateway domain>/`.

## Configuration options

### PD disaggregation

To run SGLang with [PD disaggregation](https://docs.sglang.io/advanced_features/pd_disaggregation.html), use replica groups: one for [Shepherd Model Gateway (SMG)](https://docs.sglang.io/advanced_features/sgl_model_gateway.html), one for prefill workers, and one for decode workers.

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
          - pip install smg
          - |
            smg launch \
              --host 0.0.0.0 \
              --port 8000 \
              --pd-disaggregation \
              --prefill-policy cache_aware
        resources:
          cpu: 4
        router:
          type: sglang

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

    ??? info "gRPC mode"

        SGLang workers can also connect to the SMG router over gRPC. Run the workers from an SMG image that bundles the SGLang version, pass `--grpc-mode`, and add `--enable-igw` and `--model-path` to `smg launch` so the router can register them.

        <div editor-title="pd-grpc.dstack.yml">

        ```yaml
        type: service
        name: prefill-decode

        env:
          - HF_TOKEN
          - MODEL_ID=zai-org/GLM-4.5-Air-FP8

        replicas:
          - count: 1
            # For now replica group with router must have count: 1
            python: "3.12"
            commands:
              - pip install smg
              - |
                smg launch \
                  --enable-igw \
                  --pd-disaggregation \
                  --model-path $MODEL_ID \
                  --host 0.0.0.0 \
                  --port 8000 \
                  --prefill-policy cache_aware
            router:
              type: sglang
            resources:
              cpu: 4

          - count: 1..4
            scaling:
              metric: rps
              target: 3
            image: ghcr.io/lightseekorg/smg:1.4.1-sglang-v0.5.10
            commands:
              - |
                python3 -m sglang.launch_server \
                  --model-path $MODEL_ID \
                  --host 0.0.0.0 \
                  --port 8000 \
                  --grpc-mode \
                  --disaggregation-mode prefill \
                  --disaggregation-transfer-backend nixl \
                  --disaggregation-bootstrap-port 8998
            resources:
              gpu: H200

          - count: 1..8
            scaling:
              metric: rps
              target: 2
            image: ghcr.io/lightseekorg/smg:1.4.1-sglang-v0.5.10
            commands:
              - |
                python3 -m sglang.launch_server \
                  --model-path $MODEL_ID \
                  --host 0.0.0.0 \
                  --port 8000 \
                  --grpc-mode \
                  --disaggregation-mode decode \
                  --disaggregation-transfer-backend nixl
            resources:
              gpu: H200

        port: 8000
        ```

        </div>

        To use the [Mooncake](https://github.com/kvcache-ai/Mooncake) transfer backend, set `--disaggregation-transfer-backend mooncake`.

=== "AMD"

    The example below deploys `Qwen/Qwen2.5-72B-Instruct` on a multi-node cluster with AMD MI300X GPUs:

    <div editor-title="amd-pd.dstack.yml">

    ```yaml
    type: service
    name: amd-sglang-pd-service

    image: rocm/sgl-dev:v0.5.10.post1-rocm720-mi30x-20260427
    privileged: true

    env:
      - MODEL_ID=Qwen/Qwen2.5-72B-Instruct
      - HF_TOKEN
      - SGLANG_USE_AITER=0
      - SGLANG_ROCM_FUSED_DECODE_MLA=0
      - SGLANG_DISAGGREGATION_BOOTSTRAP_TIMEOUT=600
      - SGLANG_DISAGGREGATION_WAITING_TIMEOUT=600
      - RDMA_DEVICES=bnxt_re0,bnxt_re1,bnxt_re2,bnxt_re3,bnxt_re4,bnxt_re5,bnxt_re6,bnxt_re7
      - NCCL_IB_DISABLE=1

    replicas:
      - count: 1
        commands:
          - pip install smg
          - |
            smg launch \
              --pd-disaggregation \
              --host 0.0.0.0 \
              --port 30000
        resources:
          cpu: 4..
        router:
          type: sglang

      - count: 1..2
        scaling:
          metric: rps
          target: 300
        commands:
          - |
            python3 -m sglang.launch_server \
              --model $MODEL_ID \
              --disaggregation-mode prefill \
              --disaggregation-transfer-backend mooncake \
              --host 0.0.0.0 \
              --port 30000 \
              --tp $DSTACK_GPUS_NUM \
              --trust-remote-code \
              --disaggregation-ib-device $RDMA_DEVICES \
              --disaggregation-bootstrap-port 8998 \
              --disable-radix-cache \
              --disable-cuda-graph \
              --disable-overlap-schedule \
              --mem-fraction-static 0.8 \
              --max-running-requests 1024
        resources:
          gpu: MI300X:8
          cpu: 96..
          memory: 512GB..

      - count: 1..4
        scaling:
          metric: rps
          target: 300
        commands:
          - |
            python3 -m sglang.launch_server \
              --model $MODEL_ID \
              --disaggregation-mode decode \
              --disaggregation-transfer-backend mooncake \
              --host 0.0.0.0 \
              --port 30000 \
              --tp $DSTACK_GPUS_NUM \
              --trust-remote-code \
              --disaggregation-ib-device $RDMA_DEVICES \
              --disable-radix-cache \
              --disable-cuda-graph \
              --disable-overlap-schedule \
              --decode-attention-backend triton \
              --mem-fraction-static 0.8 \
              --max-running-requests 1024
        resources:
          gpu: MI300X:8
          cpu: 96..
          memory: 512GB..

    port: 30000
    model: Qwen/Qwen2.5-72B-Instruct

    # Custom probe is required for PD disaggregation.
    probes:
      - type: http
        url: /health
        interval: 15s

    volumes:
      - /usr/lib64/libibverbs/libbnxt_re-rdmav34.so:/usr/lib/x86_64-linux-gnu/libibverbs/libbnxt_re-rdmav34.so
    ```

    </div>

    !!! info "RoCE library"
        Mooncake uses the RDMA/RoCE interconnect for KV Cache transer. To use the RDMA/RoCE interconnect on Broadcom `bnxt_re` devices, Mooncake requires the Broadcom-specific userspace provider library `libbnxt_re-rdmav34.so` to be available inside the container at `/usr/lib/x86_64-linux-gnu/libibverbs/libbnxt_re-rdmav34.so`. We make this library available by mounting the host provider library from `/usr/lib64/libibverbs/libbnxt_re-rdmav34.so`.

Currently, auto-scaling only supports `rps` as the metric. TTFT and ITL metrics are coming soon.

!!! info "Cluster"
    PD disaggregation requires the service to run in a fleet with `placement` set to `cluster`, because the replicas require an interconnect between instances.

    While the prefill and decode replicas run on GPUs, the router replica requires a CPU instance in the same cluster.

## What's next?

1. Read about [services](../../concepts/services.md) and [gateways](../../concepts/gateways.md)
2. Browse the [Qwen 3.6 SGLang cookbook](https://docs.sglang.io/cookbook/autoregressive/Qwen/Qwen3.6) and the [SGLang server arguments reference](https://docs.sglang.ai/advanced_features/server_arguments.html)
