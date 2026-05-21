---
title: "Deploying inference endpoints with PD disaggregation on AMD GPUs"
date: 2026-05-21
description: "A walkthrough of deploying PD disaggregated inference on AMD GPUs with dstack and Shepherd Model Gateway (SMG), using SGLang workers and the Mooncake Transfer Engine."
slug: amd-pd-disaggregation
image: https://dstack.ai/static-assets/static-assets/images/amd-pd-disaggregation.png
categories:
  - Changelog
---

# Deploying inference endpoints with PD disaggregation on AMD GPUs

`dstack` is an open-source, AI-native orchestrator that works across clouds, Kubernetes clusters, on-prem fleets, hardware vendors, and frameworks. Alongside training, inference is one of the primary use cases `dstack` supports out of the box.

<img src="https://dstack.ai/static-assets/static-assets/images/amd-pd-disaggregation.png" width="630" />

`dstack` recently added native support for Prefill–Decode (PD) disaggregation. It works with [Shepherd Model Gateway](smg.md) (SMG) — a high-performance inference gateway evolved from the SGLang Router — on both NVIDIA and AMD, and with [NVIDIA Dynamo](https://docs.nvidia.com/dynamo/) on NVIDIA. This post walks through deploying it on AMD GPUs with SMG.

<!-- more -->

## Why PD disaggregation

PD disaggregation is useful when a single LLM deployment has two different bottlenecks:

- **Prefill** processes the prompt. It is compute-bound, parallelizable, and has a direct impact on Time to First Token (TTFT).
- **Decode** generates tokens one by one. It is memory-bound, sequential, and has a direct impact on inter-token latency.

When the same worker handles both phases, every replica has to serve both bottlenecks. With PD disaggregation, prefill and decode run as separate pools, and each pool can be sized and scaled independently.

The tradeoff is operational: for every request, the KV cache produced by the prefill worker must be transferred to the decode worker before generation can continue. That transfer sits on the TTFT path, so the cluster needs a high-bandwidth, low-latency interconnect such as RDMA over InfiniBand or RoCE, rather than TCP over a conventional NIC.

In this walkthrough, [SMG](https://lightseek.org/smg/) routes requests between SGLang workers. On AMD, the workers use the [Mooncake Transfer Engine](https://github.com/kvcache-ai/Mooncake) to transfer KV cache over RDMA/RoCE. In the configuration we tested, the RDMA fabric is exposed by Broadcom `bnxt_re` Ethernet devices.

??? info "Prerequisites"
    Running PD disaggregation on `dstack` requires first creating a [fleet](https://dstack.ai/docs/concepts/fleets/) with `placement: cluster`, so that prefill and decode workers share a high-bandwidth interconnect. This can be a [backend fleet](https://dstack.ai/docs/concepts/fleets/#backend-fleets_1) provisioned by `dstack` on a cloud or Kubernetes cluster, or an [SSH fleet](https://dstack.ai/docs/concepts/fleets/#ssh-fleets_1) registered against bare-metal or VM hosts you already manage.

## Validating the interconnect

To measure end-to-end bandwidth across nodes, run the [NCCL/RCCL tests example](../../docs/examples/clusters/nccl-rccl-tests.md).

For a quick check that the RDMA devices are visible on a particular host, run:

<div class="termy">

```shell
$ ibv_devices
```

</div>

All eight `bnxt_re*` interfaces should be listed. Use `ibv_devinfo` to inspect port state and link details. If devices are missing or in an unexpected state, install or update the NIC driver and userspace RDMA library before proceeding.

## Deploying the service

To deploy an inference endpoint with PD disaggregation using `dstack`, define a [service](../../docs/concepts/services.md) with three replica groups: an SMG router, a pool of prefill workers, and a pool of decode workers.

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

`dstack` provisions each group, registers workers with the router, runs health probes, and autoscales prefill and decode pools independently against RPS.

Worker replicas run on GPU and bind to the Broadcom RDMA devices. While the prefill and decode replicas run on GPUs, the router replica requires a CPU instance in the same cluster.

!!! info "RoCE library"
    Mooncake uses the RDMA/RoCE interconnect for KV cache transfer. To use the RDMA/RoCE interconnect on Broadcom `bnxt_re` devices, Mooncake requires the Broadcom-specific userspace provider library `libbnxt_re-rdmav34.so` to be available inside the container at `/usr/lib/x86_64-linux-gnu/libibverbs/libbnxt_re-rdmav34.so`. We make this library available by mounting the host provider library from `/usr/lib64/libibverbs/libbnxt_re-rdmav34.so`.

Apply the configuration:

<div class="termy">

```shell
$ HF_TOKEN=...
$ dstack apply -f amd-pd.dstack.yml
```

</div>

Once provisioning completes, `dstack` exposes the service through a single endpoint:

<div class="termy">

```shell
$ curl http://localhost:3000/proxy/services/main/amd-sglang-pd-service/v1/chat/completions \
    -H 'Content-Type: application/json' \
    -H 'Authorization: Bearer <dstack token>' \
    -d '{
        "model": "Qwen/Qwen2.5-72B-Instruct",
        "messages": [
            {
                "role": "user",
                "content": "Compose a poem that explains the concept of recursion in programming."
            }
        ]
    }'
```

</div>

Requests are routed to SMG, which selects the prefill and decode workers for each request. The prefill worker processes the prompt, the decode worker continues generation, and Mooncake transfers the KV cache between them over RoCE. `dstack` registers and deregisters workers with SMG as replicas are added or removed, runs the `/health` probe on each replica, and scales each replica group independently.

!!! info "Limitations"
    - Currently, only one router replica per service is supported.
    - The example uses the SGLang inference backend for prefill and decode workers. vLLM backend support is coming soon.
    - Autoscaling supports the RPS metric. TTFT and ITL-based autoscaling support is coming soon.

## Why this matters

`dstack` provides a single, simple interface for orchestrating training and inference across hardware vendors, serving frameworks, routers, and infrastructure. It removes the need to assemble multiple fragmented tools on top of Kubernetes or build your own orchestration layer in-house.

!!! info "Benchmarks"
    Benchmarks for PD disaggregation on AMD are in progress and will be published in a follow-up. If you are running AMD GPUs and would like to contribute workloads or collaborate on benchmarking, please get in touch.

Bug reports, feedback, and feature requests are welcome on the [issue tracker](https://github.com/dstackai/dstack/issues) and on [Discord](https://discord.gg/u8SmfwPpMd).

> *Thanks to Matthew Bettinger at AMD for the collaboration, testing time, and feedback that shaped this integration.*

## What's next?

1. Read about [services](https://dstack.ai/docs/concepts/services/) and [fleets](https://dstack.ai/docs/concepts/fleets/)
2. Check the [NCCL/RCCL tests](https://dstack.ai/docs/examples/clusters/nccl-rccl-tests/) example
3. Review the [Shepherd Model Gateway](https://lightseek.org/smg/getting-started/) and [SGLang PD disaggregation](https://docs.sglang.ai/advanced_features/pd_disaggregation.html) documentation
4. Join [Discord](https://discord.gg/u8SmfwPpMd)
