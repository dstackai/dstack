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

With `dstack` `0.20.10`, you can define a service with separate replica groups for Prefill and Decode workers and enable PD disaggregation directly in the `router` configuration.

<div editor-title="glm45air.dstack.yml">

```yaml
type: service
name: glm45air

env:
  - HF_TOKEN
  - MODEL_ID=zai-org/GLM-4.5-Air-FP8

image: lmsysorg/sglang:latest

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

probes:
  - type: http
    url: /health_generate
    interval: 15s

router:
  type: sglang
  pd_disaggregation: true
```

</div>

Deploy it as usual:

<div class="termy">

```shell
$ HF_TOKEN=...
$ dstack apply -f glm45air.dstack.yml
```

</div>

### Gateway

Just like `dstack` relies on the SGLang router for cache-aware routing, Prefill–Decode disaggregation also requires a [gateway](../../docs/concepts/gateways.md#sglang) configured with the SGLang router.

<div editor-title="gateway-sglang.dstack.yml">

```yaml
type: gateway
name: inference-gateway

backends: [kubernetes]
region: any

domain: example.com

router:
  type: sglang
  policy: cache_aware
```

</div>

## Limitations

* Because the SGLang router requires all workers to be on the same network, and `dstack` currently runs the router inside the gateway, the gateway and the service must be running in the same cluster.
* Prefill–Decode disaggregation is currently available with the SGLang backend (vLLM support is coming).
* Autoscaling supports RPS as the metric for now; TTFT and ITL metrics are planned next.

With native support for inference and now Prefill–Decode disaggregation, `dstack` makes it easier to run high-throughput, low-latency model serving across GPU clouds, and Kubernetes or bare-metal clusters.

## What's next?

We’re working on PD disaggregation benchmarks and tuning guidance — coming soon.

In the meantime:

1. Read about [services](../../docs/concepts/services.md), [gateways](../../docs/concepts/gateways.md), and [fleets](../../docs/concepts/fleets.md)
2. Check out [Quickstart](../../docs/quickstart.md)
3. Join [Discord](https://discord.gg/u8SmfwPpMd)
