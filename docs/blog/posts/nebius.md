---
title: Supporting GPU provisioning and orchestration on Nebius
date: 2025-04-11
description: "TBA"  
slug: nebius
image: https://dstack.ai/static-assets/static-assets/images/dstack-nebius-v2.png
categories:
  - Changelog
---

# Supporting GPU provisioning and orchestration on Nebius

As demand for GPU compute continues to scale, open-source tools tailored for AI workloads are becoming critical to
developer velocity and efficiency.
`dstack` is an open-source orchestrator purpose-built for AI infrastructure—offering a lightweight, container-native
alternative to Kubernetes and Slurm.

<img src="https://dstack.ai/static-assets/static-assets/images/dstack-nebius-v2.png" width="630"/>

Today, we’re announcing native integration with [Nebius :material-arrow-top-right-thin:{ .external }](https://nebius.com/){:target="_blank"},
offering a streamlined developer experience for teams using GPUs for AI workloads.
<!-- more -->

## About Nebius

Nebius provides cloud GPUs,
offering high-performance clusters at competitive prices. This pricing is achieved through custom-designed hardware,
partnerships with Original Design Manufacturers (ODMs), and infrastructure team expertise.

Nebius offers various NVIDIA GPUs, including the L40S, H100, H200, GB200, NVL72, and B200 models, available on-demand
and through reserved instances. Their data centers are located across Europe, with planned expansions into the US.

## Why dstack

Kubernetes offers flexibility, but its complexity is often unnecessary—especially for use cases like interactive
development or multi-stage training.
Slurm is excellent for batch scheduling but lacks native support for dev environments, real-time inference, and
multi-user orchestration.

`dstack` fills the gap: a developer-friendly platform with native GPU support across dev environments, tasks, and
long-running services—without the operational overhead.

## Getting started

To use `dstack` with Nebius, configure your `nebius` backend:

1. Log in to your [Nebius AI Cloud :material-arrow-top-right-thin:{ .external }](https://console.eu.nebius.com/){:target="_blank"} account.  
2. Navigate to `Access`, and select  `Service Accounts`.  
3. Create a new service account, assign it to the `editors` group, and upload an authorized key.

Then, configure the backend via `~/.dstack/server/config.yml`:

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
  - name: main
    backends:
      - type: nebius
        creds:
      	  type: service_account
          service_account_id: serviceaccount-e002dwnbz81sbvg2bs
          public_key_id: publickey-e00fciu5rkoteyzo69
          private_key_file: ~/path/to/key.pem
```

</div>

Now, proceed with installing and starting the `dstack` server:

<div class="termy">

```shell
$ pip install "dstack[nebius]"
$ dstack server
```

</div>

For more details, refer to [Installation](../../docs/installation/index.md).

Use the `dstack` CLI to
manage [dev environments](../../docs/concepts/dev-environments.md), [tasks](../../docs/concepts/tasks.md),
and [services](../../docs/concepts/services.md).

<div class="termy">

```shell
$ dstack apply -f .dstack.yml

 #  BACKEND  REGION     RESOURCES                        SPOT  PRICE
 1  nebius   eu-north1  8xCPU, 32GB, 1xL40S (48GB)       no    $1.5484
 2  nebius   eu-north1  16xCPU, 200GB, 1xH100 (80GB)     no    $2.95
 3  nebius   eu-north1  16xCPU, 200GB, 1xH200 (141GB)    no    $3.5
    ...
 Shown 3 of 7 offers, $28 max
 
 Override the run? [y/n]:
```

</div>

The new `nebius` backend supports CPU and GPU instances, [fleets](../../docs/concepts/fleets.md), 
[distributed tasks](../../docs/concepts/tasks.md#distributed-tasks), and more. 
 
> Support for [network volumes](../../docs/concepts/volumes.md#network) and accelerated cluster 
interconnects is coming soon.

!!! info "What's next?"
    1. Check [Quickstart](../../docs/quickstart.md)
    2. Sign up with [Nebius AI Cloud :material-arrow-top-right-thin:{ .external }](https://console.eu.nebius.com/){:target="_blank"}
    3. Read about [dev environments](../../docs/concepts/dev-environments.md), 
        [tasks](../../docs/concepts/tasks.md), [services](../../docs/concepts/services.md), 
        and [fleets](../../docs/concepts/fleets.md)
    4. Join [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"}
