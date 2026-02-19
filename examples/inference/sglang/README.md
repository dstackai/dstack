---
title: SGLang
description: Deploying DeepSeek-R1-Distill-Llama models using SGLang on NVIDIA and AMD GPUs
---

# SGLang

This example shows how to deploy DeepSeek-R1-Distill-Llama 8B and 70B using [SGLang](https://github.com/sgl-project/sglang) and `dstack`.

## Apply a configuration

Here's an example of a service that deploys DeepSeek-R1-Distill-Llama 8B and 70B using SgLang.

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

!!! info "SGLang Model Gateway"
    If you'd like to use a custom routing policy, e.g. by leveraging the [SGLang Model Gateway](https://docs.sglang.ai/advanced_features/router.html#), create a gateway with `router` set to `sglang`. Check out [gateways](https://dstack.ai/docs/concepts/gateways#router) for more details.

> If a [gateway](https://dstack.ai/docs/concepts/gateways/) is configured (e.g. to enable auto-scaling or HTTPs, rate-limits, etc), the service endpoint will be available at `https://deepseek-r1.<gateway domain>/`.

## PD-Disaggregation

To run PD-Disaggregated inference using SGLang Model Gateway.

Create a SGLang-enabled gateway in the same network where prefill and decode workers will be deployed. Here we are using a Kubernetes cluster to ensure the gateway and workers share the same network.

```yaml
type: gateway
name: gateway-name

backend: kubernetes
region: any

# This domain will be used to access the endpoint
domain: example.com
router:
  type: sglang
```

After the gateway is ready, create a node group with at least two instances—one for the Prefill worker and one for the Decode worker—within the same Kubernetes cluster where the gateway is running. Then apply below service configuration to the GPU nodes.

```yaml
type: service
name: prefill-decode
image: lmsysorg/sglang:latest

env:
  - HF_TOKEN
  - MODEL_ID=zai-org/GLM-4.5-Air-FP8

replicas:
  - count: 1..4
    scaling:
      metric: rps
      target: 3
    commands:
      - |
        python -m sglang.launch_server \
          --model-path $MODEL_ID \
          --disaggregation-mode prefill \
          --disaggregation-transfer-backend mooncake \
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
          --disaggregation-transfer-backend mooncake \
          --host 0.0.0.0 \
          --port 8000
    resources:
      gpu: H200

port: 8000
model: zai-org/GLM-4.5-Air-FP8

# Custom probe is required for PD disaggregation
probes:
  - type: http
    url: /health_generate
    interval: 15s

router:
  type: sglang
  pd_disaggregation: true
```

## Source code

The source-code of these examples can be found in
[`examples/llms/deepseek/sglang`](https://github.com/dstackai/dstack/blob/master/examples/llms/deepseek/sglang) and [`examples/inference/sglang`](https://github.com/dstackai/dstack/blob/master/examples/inference/sglang).

## What's next?

1. Read about [services](https://dstack.ai/docs/concepts/services) and [gateways](https://dstack.ai/docs/concepts/gateways)
2. Browse the [SgLang DeepSeek Usage](https://docs.sglang.ai/references/deepseek.html), [Supercharge DeepSeek-R1 Inference on AMD Instinct MI300X](https://rocm.blogs.amd.com/artificial-intelligence/DeepSeekR1-Part2/README.html)
