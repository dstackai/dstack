---
title: Dynamo
description: Deploying zai-org/GLM-4.5-Air-FP8 using NVIDIA Dynamo
---

# Dynamo

This example shows how to deploy `zai-org/GLM-4.5-Air-FP8` using
[NVIDIA Dynamo](https://github.com/ai-dynamo/dynamo) and `dstack`.


## Apply a configuration

Here's an example of a service that deploys `zai-org/GLM-4.5-Air-FP8` using
Dynamo with PD disaggregation.

<div editor-title="service.dstack.yml">

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

> With the the `dynamo` router, you can use SGLang, vLLM, and TensorRT-LLM prefill and decode workers.

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

!!! info "Cluster"
    PD disaggregation requires the service to run in a fleet with `placement` set to `cluster`, because the replicas require an interconnect between instances.

    While the prefill and decode replicas run on GPUs, the router replica requires a CPU instance in the same cluster.

## What's next?

1. Read about [services](../../concepts/services.md) and [gateways](../../concepts/gateways.md)
2. Browse the [NVIDIA Dynamo GitHub repository](https://github.com/ai-dynamo/dynamo) and the [SGLang](./sglang.md) example
