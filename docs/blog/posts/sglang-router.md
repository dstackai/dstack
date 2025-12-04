---
title: "SGLang router integration and disaggregated inference roadmap"
date: 2025-11-25
description: "TBA"
slug: sglang-router
image: https://dstack.ai/static-assets/static-assets/images/dstack-sglang-router.png
categories:
  - Changelog
---

# SGLang router integration and disaggregated inference roadmap

[dstack](https://github.com/dstackai/dstack/) provides a streamlined way to handle GPU provisioning and workload orchestration across GPU clouds, Kubernetes clusters, or on-prem environments. Built for interoperability, dstack bridges diverse hardware and open-source tooling.

<img src="https://dstack.ai/static-assets/static-assets/images/dstack-sglang-router.png" width="630"/>

As disaggregated, low-latency inference emerges, we aim to ensure this new stack runs natively on `dstack`. To move this forward, we’re introducing native integration between dstack and [SGLang’s Model Gateway](https://docs.sglang.ai/advanced_features/router.html) (formerly known as the SGLang Router).

<!-- more -->

Although `dstack` can run on Kubernetes, it differs by offering higher-level abstractions that cover the core AI use cases: [dev environments](../../docs/concepts/dev-environments.md) for development, [tasks](../../docs/concepts/tasks.md) for training, and [services](../../docs/concepts/services.md) for inference.

## Services

Here’s an example of a service:

=== "NVIDIA"

    <div editor-title="qwen.dstack.yml">

    ```yaml
    type: service
    name: qwen

    image: lmsysorg/sglang:latest
    env:
      - HF_TOKEN
      - MODEL_ID=qwen/qwen2.5-0.5b-instruct
    commands:
      - |
        python3 -m sglang.launch_server \
        --model-path $MODEL_ID \
        --port 8000 \
        --trust-remote-code
    port: 8000
    model: qwen/qwen2.5-0.5b-instruct

    resources:
      gpu: 8GB..24GB:1
    ```

    </div>

=== "AMD"
    <div editor-title="qwen.dstack.yml">

    ```yaml
    type: service
    name: qwen

    image: lmsysorg/sglang:v0.5.5.post3-rocm700-mi30x
    env:
      - HF_TOKEN
      - MODEL_ID=qwen/qwen2.5-0.5b-instruct
    commands:
      - |
        python3 -m sglang.launch_server \
        --model-path $MODEL_ID \
        --port 8000 \
        --trust-remote-code
    port: 8000
    model: qwen/qwen2.5-0.5b-instruct

    resources:
      gpu: MI300X:1
    ```

    </div>

This service can be deployed via the following command:

<div class="termy">

```shell
$ HF_TOKEN=...
$ dstack apply -f qwen.dstack.yml
```

</div>

This deploys the service as an OpenAI-compatible endpoint and manages provisioning and replicas automatically.

## Gateways

If you'd like to enable auto-scaling, HTTPS, or use a custom domain, create a gateway:

<div editor-title="gateway.dstack.yml">

    ```yaml
    type: gateway
    name: my-gateway

    backend: aws
    region: eu-west-1

    # Specify your custom domain
    domain: example.com
    ```

</div>

This gateway can be created via the following command:

<div class="termy">

```shell
$ dstack apply -f gateway.dstack.yml
```

</div>

Once the gateway has a hostname, update your domain’s DNS settings by adding a record for `*.<gateway domain>`.

After that, if you configure [replicas and scaling](../../docs/concepts/services.md#replicas-and-scaling), the gateway will automatically scale the number of replicas and route traffic across them.

### Router

By default, the gateway uses its built-in load balancer to route traffic across replicas. With the latest release, you can instead delegate traffic routing to the [SGLang Model Gateway](https://docs.sglang.ai/advanced_features/router.html) by setting the `router` property to `sglang`:

<div editor-title="gateway.dstack.yml">

    ```yaml
    type: gateway
    name: my-gateway

    backend: aws
    region: eu-west-1

    # Specify your custom domain
    domain: example.com

    router:
      type: sglang
      policy: cache_aware
    ```

</div>

The `policy` property allows you to configure the routing policy:

* `cache_aware` &mdash; Default policy; combines cache locality with load balancing, falling back to shortest queue. 
* `power_of_two` &mdash; Samples two workers and picks the lighter one.                                               
* `random` &mdash; Uniform random selection.                                                                    
* `round_robin` &mdash; Cycles through workers in order.                                                             

With this integration, K/V cache reuse across replicas becomes possible — a key step toward low-latency inference. It also sets the path for full disaggregated inference and native auto-scaling. And fundamentally, it reflects our commitment to collaborating with the open-source ecosystem instead of reinventing its core components.

## Limitations and roadmap

Looking ahead, this integration also shapes our roadmap. Over the coming releases, we plan to expand support in several key areas:

* Enabling prefill and decode worker separation for full disaggregation (today, only standard workers are supported).
* Introducing auto-scaling based on TTFT (Time to First Token) and ITL (Inter-Token Latency), complementing the current requests-per-second scaling metric.
* Supporting multi-node replicas, enabling a single replica to span multiple nodes instead of being limited to one.
* Extending native support to more emerging inference stacks.

## What's next?

1. Check [dev environments](../../docs/concepts/dev-environments.md), 
    [tasks](../../docs/concepts/tasks.md), [services](../../docs/concepts/services.md), 
    and [gateways](../../docs/concepts/gateways.md)
2. Follow [Quickstart](../../docs/quickstart.md)
3. Join [Discord](https://discord.gg/u8SmfwPpMd)
