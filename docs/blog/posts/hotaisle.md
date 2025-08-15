---
title: Supporting Hot Aisle AMD AI Developer Cloud
date: 2025-08-11
description: "TBA"  
slug: hotaisle
image: https://dstack.ai/static-assets/static-assets/images/dstack-hotaisle.png
categories:
  - Changelog
---

# Supporting Hot Aisle AMD AI Developer Cloud

As the ecosystem around AMD GPUs matures, developers are looking for easier ways to experiment with ROCm, benchmark new architectures, and run cost-effective workloads—without manual infrastructure setup.  

`dstack` is an open-source orchestrator designed for AI workloads, providing a lightweight, container-native alternative to Kubernetes and Slurm.

<img src="https://dstack.ai/static-assets/static-assets/images/dstack-hotaisle.png" width="630"/>

Today, we’re excited to announce native integration with [Hot Aisle :material-arrow-top-right-thin:{ .external }](https://www.hotaisle.io/){:target="_blank"}, an AMD-only GPU neocloud offering VMs and clusters at highly competitive on-demand pricing.  

<!-- more -->

## About Hot Aisle

Hot Aisle is a next-generation GPU cloud built around AMD’s flagship AI accelerators.  

Highlights:

- AMD’s flagship AI-optimized accelrators
- On-demand pricing: $1.99/hour for 1-GPU VMs
- No commitment – start and stop when you want
- First AMD-only GPU backend in `dstack`

While it has already been possible to use HotAisle’s 8-GPU MI300X bare-metal clusters via [`SSH fleets`](../../docs/concepts/fleets.md#ssh-fleets), this integration now enables automated provisioning of VMs—made possible by HotAisle’s newly added API for MI300X instances.

## Why dstack

`dstack` is a new open-source container orchestrator built specifically for GPU workloads.  
It fills the gaps left by Kubernetes and Slurm when it comes to GPU provisioning and orchestration:

- Unlike Kubernetes, `dstack` offers a high-level, AI-engineer-friendly interface, and GPUs work out of the box, with no need to wrangle custom operators, device plugins, or other low-level setup.
- Unlike Slurm, it’s use-case agnostic — equally suited for training, inference, benchmarking, or even setting up long-running dev environments.
- It works across clouds and on-prem without vendor lock-in.

With the new Hot Aisle backend, you can automatically provision MI300X VMs for any workload — from experiments to production — with a single `dstack` CLI command.

## Getting started

Before configuring `dstack` to use Hot Aisle’s VMs, complete these steps:

1. Create a project via `ssh admin.hotaisle.app`
2. Get credits or approve a payment method
3. Create an API key

Then, configure the backend in `~/.dstack/server/config.yml`:

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
    - type: hotaisle
      team_handle: hotaisle-team-handle
      creds:
        type: api_key
        api_key: 9c27a4bb7a8e472fae12ab34.3f2e3c1db75b9a0187fd2196c6b3e56d2b912e1c439ba08d89e7b6fcd4ef1d3f
```

</div>

Install and start the `dstack` server:

<div class="termy">

```shell
$ pip install "dstack[server]"
$ dstack server
```

</div>

For more details, see [Installation](../../docs/installation/index.md).

Use the `dstack` CLI to
manage [dev environments](../../docs/concepts/dev-environments.md), [tasks](../../docs/concepts/tasks.md),
and [services](../../docs/concepts/services.md).

<div class="termy">

```shell
$ dstack apply -f .dstack.yml

 #  BACKEND                   RESOURCES                                     INSTANCE TYPE                     PRICE   
 1  hotaisle (us-michigan-1)  cpu=13 mem=224GB disk=12288GB MI300X:192GB:1  1x MI300X 13x Xeon Platinum 8470  $1.99
 2  hotaisle (us-michigan-1)  cpu=8 mem=224GB disk=12288GB MI300X:192GB:1   1x MI300X 8x Xeon Platinum 8470   $1.99
 
 Submit the run? [y/n]:
```

</div>

Currently, `dstack` supports 1xGPU Hot Aisle VMs. Support for 8xGPU VMs will be added once Hot Aisle supports it.

> If you prefer to use Hot Aisle’s bare-metal 8-GPU clusters with dstack, you can create an [SSH fleet](../../docs/concepts/fleets.md#ssh-fleets).
> This way, you’ll be able to run [distributed tasks](../../docs/concepts/tasks.md#distributed-tasks) efficiently across the cluster.

!!! info "What's next?"
    1. Check [Quickstart](../../docs/quickstart.md)
    2. Learn more about [Hot Aisle :material-arrow-top-right-thin:{ .external }](https://hotaisle.xyz/){:target="_blank"}
    3. Explore [dev environments](../../docs/concepts/dev-environments.md), 
        [tasks](../../docs/concepts/tasks.md), [services](../../docs/concepts/services.md), 
        and [fleets](../../docs/concepts/fleets.md)
    4. Join [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"}
