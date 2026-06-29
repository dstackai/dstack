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

    <div editor-title="service.dstack.yml">

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

    <div editor-title="service.dstack.yml">

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
          "content": "A bat and a ball cost $1.10 total. The bat costs $1.00 more than the ball. How much does the ball cost?"
        }
      ],
      "max_tokens": 1024
    }'
```

</div>

> If a [gateway](../../concepts/gateways.md) is configured (e.g. to enable auto-scaling, HTTPS, rate limits, etc.), the service endpoint will be available at `https://qwen36.<gateway domain>/`.

## Configuration options

### PD disaggregation

To run vLLM with [PD disaggregation](https://docs.vllm.ai/en/latest/serving/disagg_prefill.html), use replica groups: one for [Shepherd Model Gateway (SMG)](https://docs.sglang.io/advanced_features/sgl_model_gateway.html), one for prefill workers, and one for decode workers.

<div editor-title="pd.dstack.yml">

```yaml
type: service
name: prefill-decode

env:
  - HF_TOKEN
  - MODEL_ID=zai-org/GLM-4.5-Air-FP8

replicas:
  - count: 1
    python: "3.12"
    commands:
      - pip install smg
      - |
        smg launch \
          --pd-disaggregation \
          --model-path $MODEL_ID \
          --enable-igw \
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
    image: ghcr.io/lightseekorg/smg:1.4.1-vllm-v0.18.0
    commands:
      - |
        python3 -m vllm.entrypoints.grpc_server \
          --model "$MODEL_ID" \
          --host 0.0.0.0 \
          --port 8000 \
          --kv-transfer-config '{"kv_connector":"NixlConnector","kv_role":"kv_producer"}'
    resources:
      gpu: H200

  - count: 1..8
    scaling:
      metric: rps
      target: 2
    image: ghcr.io/lightseekorg/smg:1.4.1-vllm-v0.18.0
    commands:
      - |
        python3 -m vllm.entrypoints.grpc_server \
          --model "$MODEL_ID" \
          --host 0.0.0.0 \
          --port 8000 \
          --kv-transfer-config '{"kv_connector":"NixlConnector","kv_role":"kv_consumer"}'
    resources:
      gpu: H200

port: 8000
```

</div>

> To use the [Mooncake Transfer](https://github.com/kvcache-ai/Mooncake) backend, set `"kv_connector": "MooncakeConnector"` in `--kv-transfer-config`.

Currently, auto-scaling only supports `rps` as the metric. TTFT and ITL metrics are coming soon.

!!! info "Cluster"
    PD disaggregation requires the service to run in a fleet with `placement` set to `cluster`, because the replicas require an interconnect between instances.

    While the prefill and decode replicas run on GPUs, the router replica requires a CPU instance in the same cluster.

## What's next?

1. Read about [services](../../concepts/services.md) and [gateways](../../concepts/gateways.md)
2. Browse the [Qwen 3.5 & 3.6 vLLM recipe](https://docs.vllm.ai/projects/recipes/en/latest/Qwen/Qwen3.5.html) and the [SGLang](../inference/sglang.md) example
