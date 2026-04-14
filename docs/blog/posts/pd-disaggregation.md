---
title: "Model inference with Prefill-Decode disaggregation"
date: 2026-02-19
description: "TBA"
slug: pd-disaggregation
image: https://dstack.ai/static-assets/static-assets/images/dstack-pd-disaggregation.png
categories:
  - Changelog
links:
  - SGLang router integration: https://dstack.ai/blog/sglang-router/
---

# Model inference with Prefill-Decode disaggregation

While `dstack` started as a GPU-native orchestrator for development and training, over the last year it has increasingly brought inference to the forefront — making serving a first-class citizen.

<img src="https://dstack.ai/static-assets/static-assets/images/dstack-pd-disaggregation.png" width="630"/>

At the end of last year, we introduced [SGLang router](../posts/sglang-router.md) integration — bringing cache-aware routing to [services](../../docs/concepts/services.md). Today, building on that integration, we’re adding native Prefill–Decode (PD) disaggregation.

<!-- more -->

Unlike many PD disaggregation setups tied to Kubernetes as the control plane, dstack does not depend on Kubernetes. It’s an open-source, GPU-native orchestrator that can provision GPUs directly in your cloud accounts or on bare-metal infrastructure — while also running on top of existing Kubernetes clusters if needed.

For inference, `dstack` provides a [services](../../docs/concepts/services.md) abstraction. While remaining framework-agnostic, we integrate more deeply with leading open-source frameworks — [SGLang](https://github.com/sgl-project/sglang) being one of them for model inference.

> If you’re new to Prefill–Decode disaggregation, see the official [SGLang docs](https://docs.sglang.io/advanced_features/pd_disaggregation.html).

## Services

With `dstack` `0.20.17`, you can define a service with separate replica groups for Router, Prefill and Decode workers and run PD disaggregated Inference.

<div editor-title="glm45air.dstack.yml">

```yaml
type: service
name: glm45air

env:
  - HF_TOKEN
  - MODEL_ID=zai-org/GLM-4.5-Air-FP8

image: lmsysorg/sglang:latest

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

probes:
  - type: http
    url: /health
    interval: 15s
```

</div>

Deploy it as usual:

<div class="termy">

```shell
$ HF_TOKEN=...
$ dstack apply -f glm45air.dstack.yml
```

</div>

### SSH fleet

Create an [SSH fleet](https://dstack.ai/docs/concepts/fleets/#apply-a-configuration) that includes one CPU host for the router and one or more GPU hosts for the workers. Make sure the CPU and GPU hosts are in the same network.

<div editor-title="pd-fleet.dstack.yml">

```yaml
type: fleet
name: pd-disagg

placement: cluster

ssh_config:
  user: ubuntu
  identity_file: ~/.ssh/id_rsa
  hosts:
    - 89.169.108.16   # CPU Host (router)
    - 89.169.123.100  # GPU Host (prefill/decode workers)
    - 89.169.110.65   # GPU Host (prefill/decode workers)
```

</div>

## Limitations
* The router replica group is currently limited to `count: 1` (no HA yet). Support for multiple router replicas for HA is planned.
* Prefill–Decode disaggregation is currently available with the SGLang backend (Nvidia-dynamo and vLLM support is coming).
* Autoscaling supports RPS as the metric for now; TTFT and ITL metrics are planned next.

With native support for inference and now Prefill–Decode disaggregation, `dstack` makes it easier to run high-throughput, low-latency model serving across GPU clouds, and Kubernetes or bare-metal clusters.

## What's next?

We’re working on PD disaggregation benchmarks and tuning guidance — coming soon.

In the meantime:

1. Read about [services](../../docs/concepts/services.md), [gateways](../../docs/concepts/gateways.md), and [fleets](../../docs/concepts/fleets.md)
2. Check out [Quickstart](../../docs/quickstart.md)
3. Join [Discord](https://discord.gg/u8SmfwPpMd)
