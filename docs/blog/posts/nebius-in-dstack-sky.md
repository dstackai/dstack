---
title: Nebius joins dstack Sky GPU marketplace, first to support clusters
date: 2025-09-17
description: "TBA"  
slug: nebius-in-dstack-sky
image: https://dstack.ai/static-assets/static-assets/images/dstack-sky-nebius.png
categories:
  - Changelog
---

# Nebius joins dstack Sky GPU marketplace, first to support clusters

`dstack` is an open-source control plane for orchestrating GPU workloads. It can provision cloud VMs, run on top of Kubernetes, or manage on-prem clusters.  
If you don’t want to self-host, you can use `dstack` Sky, the managed version of `dstack` that also provides access to cloud GPUs via its marketplace.

With our latest release, we’re excited to announce that [Nebius :material-arrow-top-right-thin:{ .external }](https://nebius.com/){:target="_blank"}, leading neocloud, has joined the [dstack Sky :material-arrow-top-right-thin:{ .external }](https://sky.dstack.ai){:target="_blank"} marketplace
to offer on-demand and spot GPUs, including clusters.

<img src="https://dstack.ai/static-assets/static-assets/images/dstack-sky-nebius.png" width="630"/>

<!-- more -->

Last week we published the [state of cloud GPU](state-of-cloud-gpu-2025.md), a study of the GPU market. As noted there, Nebius is one of the few neoclouds offering GPUs at scale, including on-demand, spot, and clusters.

Since early this year, the open-source version of `dstack` has supported Nebius, making it easy to manage clusters and orchestrate compute cost-effectively. Thanks to the partnership, the integration has since matured, enabling Nebius customers to simplify operations and reduce GPU costs for both training and inference.

## About dstack Sky

With this release, Nebius officially joins `dstack` Sky. Nebius can now be used not only with your own account, but also directly via the GPU marketplace.

The marketplace lets you access Nebius GPUs without having a Nebius account. You can pay through `dstack Sky`, and switch to your own Nebius account anytime with just a few clicks.

<img src="https://dstack.ai/static-assets/static-assets/images/dstack-sky-nebius-offers.png" width="750"/>

Moreover, while the open-source version of `dstack` has supported Nebius clusters from day one,  
Nebius is the first provider to offer on-demand and spot clusters on `dstack` Sky.

## Getting started

After you [sign up :material-arrow-top-right-thin:{ .external }](https://sky.dstack.ai){:target="_blank"} with `dstack` Sky, 
you’ll be prompted to create a project and choose between the GPU marketplace or your own cloud account:

<img src="https://dstack.ai/static-assets/static-assets/images/dstack-sky-project-wizard.png" width="750"/>

Once the project is created, install the `dstack` CLI:

=== "uv"

    <div class="termy">
    
    ```shell
    $ uv tool install dstack -U
    ```

    </div>

=== "pip"

    <div class="termy">
    
    ```shell
    $ pip install dstack -U
    ```

    </div>

Now you can define [dev environments](../../docs/concepts/dev-environments.md), 
[tasks](../../docs/concepts/tasks.md), [services](../../docs/concepts/services.md), 
and [fleets](../../docs/concepts/fleets.md), then apply them with `dstack apply`.

`dstack` provisions cloud VMs, sets up environments, orchestrates runs, and handles everything required for development, training, or deployment.

To create a Nebius cluster, for example for distributed training, define the following fleet configuration:

<div editor-title="my-cluster.dstack.yml">

```yaml
type: fleet
name: my-cluster

placement: cluster
nodes: 2

backends: [nebius]

resources:
  gpu: H100:8
```

</div>

Then, create it via `dstack apply`:

<div class="termy">

```shell
$ dstack apply -f my-cluster.dstack.yml
```

</div>

Once the fleet is ready, you can run [distributed tasks](../../docs/concepts/tasks.md#distributed-tasks). 
`dstack` automatically configures drivers, networking, and fast GPU-to-GPU interconnect.

To learn more, see the [clusters](../../docs/guides/clusters.md) guide.

> `dstack` can run either on top of Kubernetes or directly on cloud VMs.  
In both cases, you don’t need to manage Kubernetes yourself—`dstack` handles all orchestration automatically, letting your team stay focused on research and development.

With Nebius joining `dstack` Sky, users can now run on-demand and spot GPUs and clusters directly through the marketplace—without needing a separate Nebius account. If you prefer to go self-hosted, you can always switch to the open-source version of `dstack`, bringing the same functionality.  

Our goal is to give teams maximum flexibility while removing the complexity of managing infrastructure. More updates are coming soon.

!!! info "What's next"
    1. Sign up with [dstack Sky :material-arrow-top-right-thin:{ .external }](https://sky.dstack.ai){:target="_blank"}
    2. Check [Quickstart](../../docs/quickstart.md)
    3. Learn more about [Nebius :material-arrow-top-right-thin:{ .external }](https://nebius.com/){:target="_blank"}
    4. Explore [dev environments](../../docs/concepts/dev-environments.md), 
        [tasks](../../docs/concepts/tasks.md), [services](../../docs/concepts/services.md), 
        and [fleets](../../docs/concepts/fleets.md)
    5. Reaad the the [clusters](../../docs/guides/clusters.md) guide
