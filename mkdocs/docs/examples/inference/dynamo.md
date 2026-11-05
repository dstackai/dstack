---
title: NVIDIA Dynamo
description: Deploying zai-org/GLM-4.5-Air-FP8 using NVIDIA Dynamo with Prefill-Decode disaggregation.
---

# Dynamo

This example shows how to deploy `zai-org/GLM-4.5-Air-FP8` using
[NVIDIA Dynamo](https://github.com/ai-dynamo/dynamo) and `dstack`.


## Apply a configuration

Here's an example of a service that deploys `zai-org/GLM-4.5-Air-FP8` using
Dynamo with PD disaggregation and vLLM workers.

<div editor-title="service.dstack.yml">

```yaml
type: service
name: dynamo-pd

env:
  - HF_TOKEN
  - MODEL_ID=zai-org/GLM-4.5-Air-FP8

groups:
  # The frontend and the workers discover each other via etcd
  - name: etcd
    replicas: 1
    commands:
      - |
        curl -fsSL https://github.com/etcd-io/etcd/releases/download/v3.5.33/etcd-v3.5.33-linux-amd64.tar.gz \
          | tar -xz -C /usr/local/bin --strip-components=1 etcd-v3.5.33-linux-amd64/etcd
      - |
        etcd \
          --data-dir /tmp/etcd \
          --listen-client-urls http://0.0.0.0:2379 \
          --advertise-client-urls http://$DSTACK_MASTER_NODE_IP:2379
    resources:
      cpu: 2

  - name: frontend
    replicas: 1
    # The vLLM image provides vLLM's GLM tool call and reasoning parsers
    image: nvcr.io/nvidia/ai-dynamo/vllm-runtime:1.5.1
    commands:
      - export ETCD_ENDPOINTS=http://${{ groups[0].replicas[0].IP_ADDRESS }}:2379
      - |
        python3 -m dynamo.frontend \
          --http-port 8000 \
          --router-mode kv \
          --dyn-chat-processor vllm \
          --enable-auto-tool-choice \
          --tool-call-parser glm45 \
          --reasoning-parser glm45
    router:
      type: dynamo
    resources:
      cpu: 4

  # Only prefill workers publish KV events, as Dynamo's decode routing ignores prefix overlap
  - name: prefill-worker
    replicas: 1..4
    scaling:
      metric: rps
      target: 3
    image: nvcr.io/nvidia/ai-dynamo/vllm-runtime:1.5.1
    commands:
      - export ETCD_ENDPOINTS=http://${{ groups[0].replicas[0].IP_ADDRESS }}:2379
      - export VLLM_NIXL_SIDE_CHANNEL_HOST=$DSTACK_MASTER_NODE_IP
      # vLLM binds the KV events endpoint only if it's a wildcard address, otherwise it connects
      - |
        python3 -m dynamo.vllm \
          --model $MODEL_ID \
          --max-model-len 65536 \
          --disaggregation-mode prefill \
          --kv-transfer-config '{"kv_connector":"NixlConnector","kv_role":"kv_producer"}' \
          --kv-events-config '{"publisher":"zmq","topic":"kv-events","endpoint":"tcp://*:20080","enable_kv_cache_events":true}'
    resources:
      gpu: H200
      disk: 200GB..

  - name: decode-worker
    replicas: 1..8
    scaling:
      metric: rps
      target: 2
    image: nvcr.io/nvidia/ai-dynamo/vllm-runtime:1.5.1
    commands:
      - export ETCD_ENDPOINTS=http://${{ groups[0].replicas[0].IP_ADDRESS }}:2379
      - export VLLM_NIXL_SIDE_CHANNEL_HOST=$DSTACK_MASTER_NODE_IP
      - |
        python3 -m dynamo.vllm \
          --model $MODEL_ID \
          --max-model-len 65536 \
          --disaggregation-mode decode \
          --kv-transfer-config '{"kv_connector":"NixlConnector","kv_role":"kv_consumer"}'
    resources:
      gpu: H200
      disk: 200GB..

port: 8000
model: zai-org/GLM-4.5-Air-FP8
```

</div>

The service consists of four replica groups:

- `etcd` runs [etcd](https://etcd.io/), which Dynamo uses for service discovery. Other groups reach it via
  [`${{ groups[0].replicas[0].IP_ADDRESS }}`](../../concepts/services.md#replica-groups).
- `frontend` runs the Dynamo frontend, which serves the OpenAI-compatible API and routes requests to the workers
  based on KV cache overlap. Because the group sets `router`, `dstack` sends the service traffic to it.
- `prefill-worker` and `decode-worker` run vLLM. The prefill workers pass the KV cache to the decode workers over NIXL.

> With the `dynamo` router, you can use SGLang, vLLM, and TensorRT-LLM prefill and decode workers.

Save the configuration as `service.dstack.yml`, then use the
[`dstack apply`](../../reference/cli/dstack/apply.md) command.

<div class="termy">

```shell
$ dstack apply -f service.dstack.yml
```

</div>

If no gateway is created, the service endpoint will be available at `<dstack server URL>/proxy/services/<project name>/<run name>/`.

<div class="termy">

```shell
curl http://127.0.0.1:3000/proxy/services/main/dynamo-pd/v1/chat/completions \
    -X POST \
    -H 'Authorization: Bearer &lt;user token&gt;' \
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

> If a [gateway](../../concepts/gateways.md) is configured (e.g. to enable auto-scaling, HTTPS, rate limits, etc.), the service endpoint will be available at `https://dynamo-pd.<gateway domain>/`.

## Configuration options

Currently, auto-scaling only supports `rps` as the metric. TTFT and ITL metrics are coming soon.

> The `scaling` property requires creating a [gateway](../../concepts/gateways.md).

!!! info "Cluster"
    PD disaggregation requires the service to run in a fleet with `placement` set to `cluster`, because the replicas require an interconnect between instances.

    While the prefill and decode replicas run on GPUs, the `etcd` and `frontend` replicas require CPU instances in the same cluster.

    For production, use instances with RDMA (InfiniBand or RoCE). Without RDMA, NIXL transfers the KV cache over TCP, which works but may be slower than recomputing the prompt on the decode worker.

## What's next?

1. Read about [services](../../concepts/services.md) and [gateways](../../concepts/gateways.md)
2. Browse the [NVIDIA Dynamo GitHub repository](https://github.com/ai-dynamo/dynamo) and the [vLLM](./vllm.md) example
