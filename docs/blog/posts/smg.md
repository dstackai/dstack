---
title: "Deploying SGLang with PD disaggregation via Shepherd Model Gateway"
date: 2026-04-29
description: "TBA"
slug: smg
image: https://dstack.ai/static-assets/static-assets/images/smg.png
categories:
  - Changelog
---

# Deploying SGLang with PD disaggregation via Shepherd Model Gateway

`dstack` is an open-source control plane that simplifies GPU orchestration for both training and inference — across cloud providers, hardware vendors, and frameworks. Over the past year, we've been steadily making inference a first-class citizen in dstack.

<img src="https://dstack.ai/static-assets/static-assets/images/smg.png" width="630"/>

<!-- more -->

## About SMG

Today, we're taking the next step: native support for [Shepherd Model Gateway](https://lightseek.org/smg/) (SMG) — a high-performance inference gateway that has evolved from the SGLang Router into a standalone project under the [LightSeek Foundation](https://lightseek.org/). With the latest update, deploying SGLang with Prefill-Decode disaggregation on `dstack` becomes simpler and more flexible.

Now a standalone project, SMG aims to support various serving backends — including SGLang, vLLM, and TensorRT-LLM. Written in Rust, it provides cache-aware routing, PD disaggregation, circuit breakers, rate limiting, and 40+ Prometheus metrics out of the box.

!!! info "PD disaggregation"
    Prefill-Decode disaggregation separates the two phases of LLM inference — prompt processing (prefill) and token generation (decode). Prefill is compute-bound and parallel; decode is memory-bound and sequential. Running them separately improves both Time to First Token (TTFT) and end-to-end latency.

Since 0.20.17, `dstack` supports deploying SGLang with PD disaggregation using Shepherd Model Gateway. To do it, define three replica groups: one for SMG, one for prefill workers, and one for decode workers.

## How to use SMG with dstack

Here's a complete service configuration that deploys `zai-org/GLM-4.5-Air-FP8` with PD disaggregation using SMG and SGLang on `dstack`:

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

The SMG replica group must define `router: sglang`.

The configuration defines three replica groups. The first runs SMG as the router on a CPU node. The second and third run prefill and decode workers respectively, using [NIXL](https://github.com/ai-dynamo/nixl) for KV cache transfer between them. Prefill scales from 1 to 4 replicas and decode from 1 to 8, both based on requests per second.

```
$ HF_TOKEN=...
$ dstack apply -f prefill-decode.dstack.yml
```

Because `dstack` is not tied to any specific cloud or cluster manager, this same configuration works across any GPU cloud, any Kubernetes cluster, or any non-Kubernetes on-prem environment managed through `dstack` [fleets](../../docs/concepts/fleets.md).

## What's coming next

We're actively working on expanding the inference stack in `dstack`. Here's what's coming:

- **gRPC** — enabling SMG's gRPC mode, which will also allow using vLLM with Shepherd Model Gateway for PD disaggregation.
- **NVIDIA Dynamo** — native support for NVIDIA's inference framework.
- **TTFT and ITL** — autoscaling based on Time to First Token and Inter-Token Latency, complementing the current RPS metric.
- **AMD** — validated configurations for running PD disaggregation on AMD Instinct GPUs.

## Why vendor-agnostic?

The inference stack is evolving fast — new serving engines, new routing strategies, new hardware. Teams shouldn't have to rebuild their orchestration every time a piece of the stack changes. `dstack` provides a stable, vendor-agnostic layer that lets you adopt the best tools for each job — whether that's SGLang or vLLM, NVIDIA or AMD, cloud or on-prem — without locking into any single vendor's platform.

> Our commitment remains the same: simplify both training and inference across vendors through open-source.

*Huge thanks to the SGLang community for collaboration and support. The gateway's evolution into a standalone project have been instrumental in making this integration possible.*

!!! info "What's next?"
    1. Read about [services](https://dstack.ai/docs/concepts/services/), [gateways](https://dstack.ai/docs/concepts/gateways/), and [fleets](https://dstack.ai/docs/concepts/fleets/)
    2. Follow [Quickstart](https://dstack.ai/docs/quickstart/)
    3. Check out the [Shepherd Model Gateway](https://lightseek.org/smg/getting-started/) and [SGLang PD disaggregation](https://sgl-project.github.io/advanced_features/pd_disaggregation.html) documentation
    4. Join [Discord](https://discord.gg/u8SmfwPpMd)
