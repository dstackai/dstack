---
title: "Deploying NVIDIA Dynamo PD disaggregation with dstack"
date: 2026-06-10
description: "Deploy NVIDIA Dynamo with Prefill-Decode disaggregation using dstack services."
slug: nvidia-dynamo
image: https://dstack.ai/static-assets/static-assets/images/nvidia-dynamo.png
categories:
  - Changelog
---

# Deploying NVIDIA Dynamo PD disaggregation with dstack

`dstack` is an open-source, AI-native orchestrator that works across clouds, Kubernetes clusters, on-prem fleets, hardware vendors, and frameworks. Alongside training, inference is one of the primary use cases `dstack` supports out of the box.

With the latest update, `dstack` added native support for NVIDIA Dynamo with Prefill-Decode (PD) disaggregation, letting a service run a Dynamo router, prefill workers, and decode workers as separate replica groups.

<img src="https://dstack.ai/static-assets/static-assets/images/nvidia-dynamo.png" width="630" />

<!-- more -->

## About NVIDIA Dynamo

[NVIDIA Dynamo](https://docs.nvidia.com/dynamo/getting-started/introduction) is an open-source, high-throughput, low-latency inference framework for serving generative AI workloads in distributed environments. It adds a system-level layer above inference engines such as SGLang, vLLM, and TensorRT-LLM, coordinating them across GPUs and nodes.

Dynamo brings together disaggregated serving, intelligent routing, KV cache management, KV cache transfer, and automatic scaling to maximize throughput and minimize latency for LLM, reasoning, multimodal, and video generation workloads.

!!! info "PD disaggregation"
    Prefill-Decode disaggregation separates the two phases of LLM inference: prompt processing (prefill) and token generation (decode). Prefill is compute-bound and parallelizable. Decode is memory-bound and sequential. Running them as separate pools allows each phase to be sized and scaled independently.

## PD disaggregation with dstack

To deploy NVIDIA Dynamo with PD disaggregation, define a [service](../../docs/concepts/services.md) with three [replica groups](../../docs/concepts/services.md#replicas-and-scaling):

- a Dynamo router
- prefill workers
- decode workers

The router replica group declares `router: { type: dynamo }`. This tells `dstack` to route external traffic only to the router replica and to inject `DSTACK_ROUTER_INTERNAL_IP` into the worker replicas after the router is provisioned.

This support was introduced in [`0.20.20`](https://github.com/dstackai/dstack/releases/tag/0.20.20).

??? info "Prerequisites"
    Running PD disaggregation on `dstack` requires a [fleet](../../docs/concepts/fleets.md) with [cluster placement](../../docs/concepts/fleets.md#cluster-placement), because prefill and decode workers need a fast interconnect for KV cache transfer.

    The prefill and decode replicas run on GPUs. The router replica can run on CPU, but it must run in the same cluster.

## Deploying the service

Here's a complete service configuration that deploys `zai-org/GLM-4.5-Air-FP8` with NVIDIA Dynamo, SGLang workers, and PD disaggregation on `dstack`:

<div editor-title="dynamo-pd.dstack.yml">

```yaml
type: service
name: dynamo-pd

env:
  - HF_TOKEN
  - MODEL_ID=zai-org/GLM-4.5-Air-FP8

replicas:
  - count: 1
    docker: true
    commands:
      - apt-get update
      - apt-get install -y python3-dev python3-venv
      - python3 -m venv ~/dyn-venv
      - source ~/dyn-venv/bin/activate
      - pip install -U pip
      - pip install "ai-dynamo[sglang]==1.1.1"
      - git clone https://github.com/ai-dynamo/dynamo.git
      # Brings up the NATS / etcd compose stack and runs the Dynamo HTTP frontend.
      - docker compose -f dynamo/deploy/docker-compose.yml up -d
      - |
        python3 -m dynamo.frontend \
          --http-host 0.0.0.0 --http-port 8000 \
          --discovery-backend etcd --router-mode kv \
          --kv-cache-block-size 64
    resources:
      cpu: 4
    router:
      type: dynamo

  - count: 1..4
    scaling:
      metric: rps
      target: 3
    python: "3.12"
    nvcc: true
    commands:
      # dstack injects DSTACK_ROUTER_INTERNAL_IP after the router replica
      # is provisioned. Compose the etcd/NATS endpoints from it.
      - export ETCD_ENDPOINTS="http://$DSTACK_ROUTER_INTERNAL_IP:2379"
      - export NATS_SERVER="nats://$DSTACK_ROUTER_INTERNAL_IP:4222"
      # Set to enable /health endpoint required by dstack probes.
      - export DYN_SYSTEM_PORT="8000"
      # Wait until the router's etcd and NATS ports are actually accepting connections.
      - |
        until (echo > /dev/tcp/$DSTACK_ROUTER_INTERNAL_IP/2379) 2>/dev/null \
           && (echo > /dev/tcp/$DSTACK_ROUTER_INTERNAL_IP/4222) 2>/dev/null; do
          echo "waiting for etcd/NATS on $DSTACK_ROUTER_INTERNAL_IP..."; sleep 3
        done
      - pip install "ai-dynamo[sglang]==1.1.1"
      - |
        python3 -m dynamo.sglang \
          --model-path $MODEL_ID --served-model-name $MODEL_ID \
          --discovery-backend etcd --host 0.0.0.0 \
          --page-size 64 \
          --disaggregation-mode prefill --disaggregation-transfer-backend nixl
    resources:
      gpu: H200

  - count: 1..8
    scaling:
      metric: rps
      target: 2
    python: "3.12"
    nvcc: true
    commands:
      - export ETCD_ENDPOINTS="http://$DSTACK_ROUTER_INTERNAL_IP:2379"
      - export NATS_SERVER="nats://$DSTACK_ROUTER_INTERNAL_IP:4222"
      - export DYN_SYSTEM_PORT="8000"
      - |
        until (echo > /dev/tcp/$DSTACK_ROUTER_INTERNAL_IP/2379) 2>/dev/null \
           && (echo > /dev/tcp/$DSTACK_ROUTER_INTERNAL_IP/4222) 2>/dev/null; do
          echo "waiting for etcd/NATS on $DSTACK_ROUTER_INTERNAL_IP..."; sleep 3
        done
      - pip install "ai-dynamo[sglang]==1.1.1"
      - |
        python3 -m dynamo.sglang \
          --model-path $MODEL_ID --served-model-name $MODEL_ID \
          --discovery-backend etcd --host 0.0.0.0 \
          --page-size 64 \
          --disaggregation-mode decode --disaggregation-transfer-backend nixl
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

The router replica group starts the Dynamo HTTP frontend and the NATS/etcd compose stack used by the workers. It declares `router: { type: dynamo }`, so `dstack` treats it as the service router.

The prefill and decode replica groups use the router's internal IP to set `ETCD_ENDPOINTS` and `NATS_SERVER`, wait for those services to become reachable, then start `dynamo.sglang` in either `prefill` or `decode` mode. `DYN_SYSTEM_PORT=8000` exposes the `/health` endpoint required by the `dstack` [probe](../../docs/concepts/services.md#probes).

In this setup, Dynamo uses etcd for worker discovery and NATS for worker and KV-cache events used by the router. NIXL handles KV cache transfer between prefill and decode workers. `dstack` handles provisioning, service exposure, health probes, and independent scaling of the prefill and decode replica groups.

> With the `dynamo` router, `dstack` can run SGLang, vLLM, or TensorRT-LLM prefill and decode workers.

Apply the configuration:

<div class="termy">

```shell
$ HF_TOKEN=...
$ dstack apply -f dynamo-pd.dstack.yml
```

</div>

Once provisioning completes, `dstack` exposes a single OpenAI-compatible endpoint. Without a gateway, the endpoint is available through the server proxy:

<div class="termy">

```shell
$ curl http://127.0.0.1:3000/proxy/services/main/dynamo-pd/v1/chat/completions \
    -X POST \
    -H 'Authorization: Bearer <dstack token>' \
    -H 'Content-Type: application/json' \
    -d '{
      "model": "zai-org/GLM-4.5-Air-FP8",
      "messages": [
        {
          "role": "user",
          "content": "What is prefill-decode disaggregation?"
        }
      ],
      "max_tokens": 1024
    }'
```

</div>

If a [gateway](../../docs/concepts/gateways.md) is configured, the service endpoint is available at `https://dynamo-pd.<gateway domain>/`.

!!! info "Limitations"
    - The router replica group must use `count: 1`.
    - Services with a Dynamo router cannot configure `retry`, because workers cache the router's internal IP at provisioning time.
    - In-place updates are blocked when they would replace the Dynamo router replica. If the router gets a new internal IP, already-running workers would still point to the old etcd and NATS endpoints. Stop the run and apply again for router-affecting changes.
    - Autoscaling supports the RPS metric. TTFT and ITL-based autoscaling support is coming soon.

## Why this matters

Dynamo brings system-level inference optimizations such as disaggregated serving, KV-aware routing, and fast KV cache transfer to multi-node deployments. `dstack` provides the orchestration layer around it: provisioning the right instances, keeping router and workers in the same cluster, exposing one endpoint, running health probes, and scaling the worker groups independently.

For teams running inference, this removes another layer of glue code from the deployment path. The same `dstack` primitives used for training and development, including [fleets](../../docs/concepts/fleets.md), [services](../../docs/concepts/services.md), and [gateways](../../docs/concepts/gateways.md), can now orchestrate Dynamo-based inference across GPU clouds, Kubernetes clusters, and on-prem environments.

## What's next?

1. Read the [NVIDIA Dynamo example](../../docs/examples/inference/dynamo.md)
2. Read about [services](../../docs/concepts/services.md), [fleets](../../docs/concepts/fleets.md), and [gateways](../../docs/concepts/gateways.md)
3. Review the [NVIDIA Dynamo documentation](https://docs.nvidia.com/dynamo/getting-started/introduction) and [Dynamo GitHub repository](https://github.com/ai-dynamo/dynamo)
4. Join [Discord](https://discord.gg/u8SmfwPpMd)
