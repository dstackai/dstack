---
title: SGLang
description: Deploying DeepSeek-R1-Distill-Llama models using SGLang on NVIDIA and AMD GPUs
---

# SGLang

This example shows how to deploy DeepSeek-R1-Distill-Llama 8B and 70B using [SGLang](https://github.com/sgl-project/sglang) and `dstack`.

## Apply a configuration

Here's an example of a service that deploys DeepSeek-R1-Distill-Llama 8B and 70B using SGLang.

=== "NVIDIA"

    <div editor-title="examples/inference/sglang/nvidia/.dstack.yml">

    ```yaml
    type: service
    name: deepseek-r1

    image: lmsysorg/sglang:latest
    env:
      - MODEL_ID=deepseek-ai/DeepSeek-R1-Distill-Llama-8B

    commands:
      - python3 -m sglang.launch_server
         --model-path $MODEL_ID
         --port 8000
         --trust-remote-code

    port: 8000
    model: deepseek-ai/DeepSeek-R1-Distill-Llama-8B

    resources:
       gpu: 24GB
    ```
    </div>

=== "AMD"

    <div editor-title="examples/inference/sglang/amd/.dstack.yml">

    ```yaml
    type: service
    name: deepseek-r1

    image: lmsysorg/sglang:v0.4.1.post4-rocm620
    env:
      - MODEL_ID=deepseek-ai/DeepSeek-R1-Distill-Llama-70B

    commands:
      - python3 -m sglang.launch_server
         --model-path $MODEL_ID
         --port 8000
         --trust-remote-code

    port: 8000
    model: deepseek-ai/DeepSeek-R1-Distill-Llama-70B

    resources:
      gpu: MI300x
      disk: 300GB
    ```
    </div>

To run a configuration, use the [`dstack apply`](https://dstack.ai/docs/reference/cli/dstack/apply.md) command.

<div class="termy">

```shell
$ dstack apply -f examples/llms/deepseek/sglang/amd/.dstack.yml

 #  BACKEND  REGION     RESOURCES                         SPOT  PRICE
 1  runpod   EU-RO-1   24xCPU, 283GB, 1xMI300X (192GB)    no    $2.49

Submit the run deepseek-r1? [y/n]: y

Provisioning...
---> 100%
```
</div>

If no gateway is created, the service endpoint will be available at `<dstack server URL>/proxy/services/<project name>/<run name>/`.

<div class="termy">

```shell
curl http://127.0.0.1:3000/proxy/services/main/deepseek-r1/v1/chat/completions \
    -X POST \
    -H 'Authorization: Bearer &lt;dstack token&gt;' \
    -H 'Content-Type: application/json' \
    -d '{
      "model": "deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
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

!!! info "Run router and workers separately"
    To run the SGLang router and workers separately, use replica groups (router as a CPU replica group, workers as GPU replica groups). See [PD disaggregation](#pd-disaggregation).

> If a [gateway](https://dstack.ai/docs/concepts/gateways/) is configured (e.g. to enable auto-scaling, HTTPS, rate limits, etc.), the service endpoint will be available at `https://deepseek-r1.<gateway domain>/`.

## Configuration options

### PD disaggregation

To run SGLang with [PD disaggregation](https://docs.sglang.io/advanced_features/pd_disaggregation.html), run the **router as a replica** on a CPU-only host, while running **prefill/decode workers** as replicas on GPU hosts.

<div editor-title="examples/inference/sglang/pd.dstack.yml">

```yaml
type: service
name: prefill-decode
image: lmsysorg/sglang:latest

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

#### Fleet

Create a [fleet](https://dstack.ai/docs/concepts/fleets/) that can provision both a CPU node (for the router replica group) and GPU nodes (for the prefill/decode replica groups).
You can create an SSH fleet, elastic Cloud fleet (nodes: 0..) or kubernetes cluster. Just don't specify any resource constraints in the fleet, and dstack will automatically provision the correct instances (both CPU and GPU, in the same fleet) based on the resources specified in replicas in the run configuration.

The only requirement is that the router and worker replicas run in the same network. In practice, this typically means using a single fleet where the backend and region are the same or using `placement: cluster` if the backend supports it.

!!! note "Gateway-based routing (deprecated)"
    If you create a gateway with the [`sglang` router](https://dstack.ai/docs/concepts/gateways/#sglang), you can also run SGLang with PD disaggregation. This method is deprecated and will be disallowed in a future release in favor of running the router as a replica.

## Source code

The source-code of these examples can be found in
[`examples/llms/deepseek/sglang`](https://github.com/dstackai/dstack/blob/master/examples/llms/deepseek/sglang) and [`examples/inference/sglang`](https://github.com/dstackai/dstack/blob/master/examples/inference/sglang).

## What's next?

1. Read about [services](https://dstack.ai/docs/concepts/services) and [gateways](https://dstack.ai/docs/concepts/gateways)
2. Browse the [SgLang DeepSeek Usage](https://docs.sglang.ai/references/deepseek.html), [Supercharge DeepSeek-R1 Inference on AMD Instinct MI300X](https://rocm.blogs.amd.com/artificial-intelligence/DeepSeekR1-Part2/README.html)
