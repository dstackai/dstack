---
title: "Supporting ARM and NVIDIA GH200 on Lambda"
date: 2025-05-12
description: "TBA"
slug: gh200-on-lambda
image: https://dstack.ai/static-assets/static-assets/images/dstack-arm--gh200-lambda-min.png
categories:
  - Changelog
---

# Supporting ARM and NVIDIA GH200 on Lambda

The latest update to `dstack` introduces support for NVIDIA GH200 instances on [Lambda](../../docs/concepts/backends.md#lambda)
and enables ARM-powered hosts, including GH200 and GB200, with [SSH fleets](../../docs/concepts/fleets.md#ssh).

<img src="https://dstack.ai/static-assets/static-assets/images/dstack-arm--gh200-lambda-min.png" width="630"/>

<!-- more -->

## ARM support

Previously, `dstack` only supported x86 architecture with both cloud providers as well as on-prem clusters. With the latest update, it’s now possible to use both cloud and SSH fleets with ARM-based CPUs too. To request ARM CPUs in a run or fleet configuration, specify the arm architecture in the `resources`.`cpu` property:

```yaml
resources:
  cpu: arm:4..  # 4 or more ARM cores
```

If the hosts in an SSH fleet have ARM CPUs, `dstack` will automatically detect both ARM-based CPUs as well as ARM-based GPU Superchips such as GH200 and enable their use.

To see available offers with ARM CPUs, pass `--cpu arm` to the `dstack offer` command.

## About GH200

NVIDIA Grace is the first NVIDIA data center CPU, built on top of ARM specifically for AI workloads. The NVIDIA GH200 Superchip brings together a 72-core NVIDIA Grace CPU with an NVIDIA H100 GPU, connected with a high-bandwidth, memory-coherent NVIDIA NVLink-C2C interconnect.

| CPU           | GPU  | CPU Memory               | GPU Memory         | NVLink-C2C |
| ------------- | ---- | ------------------------ | ------------------ | ---------- |
| Grace 72-core | H100 | 480GB LPDDR5X at 512GB/s | 96GB HBM3 at 4TB/s | 900GB/s    |

The GH200 Superchip’s 450 GB/s bidirectional bandwidth enables KV cache offloading to CPU memory. While prefill can leverage CPU memory for optimizations like prefix caching, generation benefits from the GH200’s higher memory bandwidth.

## GH200 on Lambda

[Lambda :material-arrow-top-right-thin:{ .external }](https://cloud.lambda.ai/sign-up?_gl=1*1qovk06*_gcl_au*MTg2MDc3OTAyOS4xNzQyOTA3Nzc0LjE3NDkwNTYzNTYuMTc0NTQxOTE2MS4xNzQ1NDE5MTYw*_ga*MTE2NDM5MzI0My4xNzQyOTA3Nzc0*_ga_43EZT1FM6Q*czE3NDY3MTczOTYkbzM0JGcxJHQxNzQ2NzE4MDU2JGo1NyRsMCRoMTU0Mzg1NTU1OQ..){:target="_blank"} provides secure, user-friendly, reliable, and affordable cloud GPUs. Since end of last year, Lambda started to offer on-demand GH200 instances through their public cloud. Furthermore, they offer these instances at the promotional price of $1.49 per hour until June 30th 2025.

With the latest `dstack` update, it’s now possible to use these instances with your Lambda account whether you’re running a dev environment, task, or service:

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment
name: my-env
image: nvidia/cuda:12.8.1-base-ubuntu20.04
ide: vscode

resources:
  gpu: GH200:1
```

</div>

> Note, you have to use an ARM-based Docker image.

To determine whether Lambda has GH200 on-demand instances available, run `dstack apply`:

<div class="termy">

```shell
$ dstack apply -f .dstack.yml

 #   BACKEND             RESOURCES                          INSTANCE TYPE  PRICE
 1   lambda (us-east-3)  cpu=arm:64 mem=464GB GH200:96GB:1  gpu_1x_gh200   $1.49
```

</div>

!!! info "Retry policy"
    Note, if GH200s are not  available at the moment, you can specify the [retry policy](../../docs/concepts/dev-environments.md#retry-policy) in your run configuration so that `dstack` can run the configuration once the GPU becomes available.

> If you have GH200 or GB200-powered hosts already provisioned via Lambda, another cloud provider, or on-prem, you can now use them with [SSH fleets](../../docs/concepts/fleets.md#ssh).

!!! info "What's next?"
    1. Sign up with [Lambda :material-arrow-top-right-thin:{ .external }](https://cloud.lambda.ai/sign-up?_gl=1*1qovk06*_gcl_au*MTg2MDc3OTAyOS4xNzQyOTA3Nzc0LjE3NDkwNTYzNTYuMTc0NTQxOTE2MS4xNzQ1NDE5MTYw*_ga*MTE2NDM5MzI0My4xNzQyOTA3Nzc0*_ga_43EZT1FM6Q*czE3NDY3MTczOTYkbzM0JGcxJHQxNzQ2NzE4MDU2JGo1NyRsMCRoMTU0Mzg1NTU1OQ..){:target="_blank"}
    2. Set up the [Lambda](../../docs/concepts/backends.md#lambda) backend
    3. Follow [Quickstart](../../docs/quickstart.md)
    4. Check [dev environments](../../docs/concepts/dev-environments.md), [tasks](../../docs/concepts/tasks.md), [services](../../docs/concepts/services.md), and [fleets](../../docs/concepts/fleets.md)
