---
title: Introducing service probes
date: 2025-08-14
description: HTTP readiness probes for services, inspired by Kubernetes—safer rollouts and clear runtime visibility.
slug: probes
image: https://dstack.ai/static-assets/static-assets/images/dstack-service-probes.png
categories:
  - Changelog
---

# Introducing service probes

`dstack` services are long-running workloads—most often inference endpoints and sometimes web apps—that run continuously on GPU or CPU instances. They can scale across replicas and support rolling deployments.

This release adds HTTP probes inspired by Kubernetes readiness probes. Probes periodically call an endpoint on each replica (for example, `/health`) to confirm it responds as expected. The result gives clear visibility into startup progress and, during rolling deployments, ensures traffic only shifts to a replacement replica after all configured probes have proven ready.

<img src="https://dstack.ai/static-assets/static-assets/images/dstack-service-probes.png" width="630"/>

<!-- more -->

When a service starts, replicas may need time to load models and initialize dependencies. Without probes, a replica is considered ready as soon as the container starts. With probes, readiness is based on real responses.

Each probe sends an HTTP request to a configured endpoint at a set interval. A `2xx` response counts as success.

## Configuration

Probes can be set via the `probes` property in a service configuration:

<div editor-title="service.dstack.yml">

```yaml
type: service
name: llama31

python: 3.12
env:
  - HF_TOKEN
commands:
  - uv pip install vllm
  - |
    vllm serve meta-llama/Meta-Llama-3.1-8B-Instruct \
      --max-model-len 4096 \
      --tensor-parallel-size $DSTACK_GPUS_NUM
port: 8000
model: meta-llama/Meta-Llama-3.1-8B-Instruct

probes:
  - type: http
    url: /health
    interval: 15s

replicas: 2

resources:
  gpu: 24GB..48GB
```
</div>

In this example, `dstack` sends a GET `/health` request every 15 seconds to each replica.

## Probe status

<div class="termy">

```shell
$ dstack ps --verbose

 NAME                            BACKEND          STATUS   PROBES  SUBMITTED
 llama31 deployment=1                             running          11 mins ago
   replica=0 job=0 deployment=0  aws (us-west-2)  running  ✓       11 mins ago
   replica=1 job=0 deployment=1  aws (us-west-2)  running  ×       1 min ago
```

</div>

In `dstack ps --verbose`, a replica shows `×` if the last probe failed, `~` while probes are succeeding but the [`ready_after`](../../docs/reference/dstack.yml/service.md#ready_after) threshold is not yet reached, and `✓` once the last `ready_after` checks have succeeded. Probes run for each replica while it is `running`.

## Advanced configuration

Probes support custom HTTP methods, headers (with environment variable interpolation), request bodies, timeouts, and multiple checks in sequence. For example:

```yaml
env:
  - PROBES_API_KEY
probes:
  - type: http
    method: post
    url: /check-health
    headers:
      - name: X-API-Key
        value: ${{ env.PROBES_API_KEY }}
      - name: Content-Type
        value: application/json
    body: '{"level": 2}'
    timeout: 20s
```

Note: request bodies are not allowed with `GET` or `HEAD` methods.

## Rolling deployments

During a rolling deployment, `dstack` starts a replacement replica, waits for it to be `running` and to pass its probes, then retires the old replica. This preserves availability while large models warm up.

Probes give you visibility about health of each replica. During rolling updates they gate traffic so new replicas receive requests after their checks pass.

See [services](../../docs/concepts/services.md#probes) and the [reference](../../docs/reference/dstack.yml/service.md#probes) for all options.

!!! info "What's next?"
    1. Check [Quickstart](../../docs/quickstart.md)
    2. Learn about [services](../../docs/concepts/services.md)
    3. Join [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"}
