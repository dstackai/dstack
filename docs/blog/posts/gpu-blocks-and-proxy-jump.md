---
title: Introducing GPU blocks and proxy jump for SSH fleets
date: 2025-02-18
description: "TBA"  
slug: gpu-blocks-and-proxy-jump
image: https://dstack.ai/static-assets/static-assets/images/data-centers-and-private-clouds.png
categories:
  - Changelog
---

# Introducing GPU blocks and proxy jump for SSH fleets

Recent breakthroughs in open-source AI have made AI infrastructure accessible beyond public clouds, driving demand for
running AI workloads in on-premises data centers and private clouds. 
This shift offers organizations both high-performant clusters and flexibility and control.

However, Kubernetes, while a popular choice for traditional deployments, is often too complex and low-level to address
the needs of AI teams.

Originally, `dstack` was focused on public clouds. With the new release, `dstack`
extends support to data centers and private clouds, offering a simpler, AI-native solution that replaces Kubernetes and
Slurm.

<img src="https://dstack.ai/static-assets/static-assets/images/data-centers-and-private-clouds.png" width="630"/>

<!-- more -->

Private clouds offer the scalability and performance needed for large GPU clusters, while on-premises data centers
provide stronger security and privacy controls.  

In both cases, the focus isn’t just on seamless orchestration but also on maximizing infrastructure efficiency. This has
long been a strength of Kubernetes, which enables concurrent workload execution across provisioned nodes to minimize
resource waste.

### GPU blocks

The newest version of `dstack` introduces a feature called [GPU blocks](../../docs/concepts/fleets.md#ssh-blocks), bringing this level of efficiency to `dstack`. It
enables optimal hardware utilization by allowing concurrent workloads to run on the same hosts, using slices of the
available resources on each host.

> For example, imagine you’ve reserved a cluster with multiple bare-metal nodes, each equipped with 8x MI300X GPUs from
[Hot Aisle :material-arrow-top-right-thin:{ .external }](https://hotaisle.xyz/){:target="_blank"}.

With `dstack`, you can define your fleet configuration like this:

<div editor-title="my-hotaisle-fleet.dstack.yml">

```yaml
type: fleet
name: my-hotaisle-fleet

ssh_config:
  user: ubuntu
  identity_file: ~/.ssh/hotaisle_id_rsa
  hosts:
    - hostname: ssh.hotaisle.cloud
      port: 22013
      blocks: auto
    - hostname: ssh.hotaisle.cloud
      port: 22014
      blocks: auto
  
placement: cluster
```

</div>

When you run `dstack apply`, each host appears as an available fleet instance, showing `0/8` next to `busy`. By setting `blocks`
to `auto`, you automatically slice each host into 8 GPU blocks.

<div class="termy">

```shell
$ dstack apply -f my-hotaisle-fleet.dstack.yml

Provisioning...
---> 100%

 FLEET              INSTANCE  RESOURCES         STATUS     CREATED 
 my-hotaisle-fleet  0         8xMI300X (192GB)  0/8 busy   3 mins ago      
                    1         8xMI300X (192GB)  0/8 busy   3 mins ago    
```

</div>

For instance, you can run two workloads, each using 4 GPUs, and `dstack` will execute them concurrently on a single instance.

As the fleet owner, you can set the `blocks` parameter to any number. If you set it to `2`, `dstack` will slice each
host into 2 blocks, each with 4 GPUs. This flexibility allows you to define the minimum block size, ensuring the most
efficient utilization of your resources.

!!! info "Fractional GPU"
    While we plan to eventually support fractions of a single GPU too, this is not the primary use case, as most modern AI
    teams require full GPUs for their workloads.

Regardless whether you're using dstack with a data center or a private cloud, once a fleet is created, 
you’re free to run [dev environments](../../docs/concepts/dev-environments.md),
[tasks](../../docs/concepts/tasks.md), and [services](../../docs/concepts/services.md) while maximizing the
cost-efficiency of GPU utilization by concurrent runs.

## Proxy jump

Private clouds typically provide access to GPU clusters via SSH through a login node. In these setups, only the login
node is internet-accessible, while cluster nodes can only be reached via SSH from the login node. This prevents creating
an SSH fleet by directly listing the cluster nodes' hostnames.

The latest `dstack` release introduces the [`proxy_jump`](../../docs/concepts/fleets.md#proxy-jump) property in SSH fleet configurations, enabling creating fleets 
through a login node.

> For example, imagine you’ve reserved a 1-Click Cluster from
> [Lambda :material-arrow-top-right-thin:{ .external }](https://lambdalabs.com/){:target="_blank"} with multiple nodes, each equipped with 8x H100 GPUs from.

With `dstack`, you can define your fleet configuration like this:

<div editor-title="my-lambda-fleet.dstack.yml">

```yaml
type: fleet
name: my-lambda-fleet

ssh_config:
  user: ubuntu
  identity_file: ~/.ssh/lambda_node_id_rsa
  hosts:
    - us-east-2-1cc-node-1
    - us-east-2-1cc-node-2
    - us-east-2-1cc-node-3
    - us-east-2-1cc-node-4
  proxy_jump: 
    hostname: 12.34.567.890
    user: ubuntu
    identity_file: ~/.ssh/lambda_head_id_rsa

placement: cluster
```

</div>

When you run `dstack apply`, `dstack` creates an SSH fleet and connects to the configured hosts through the login node
specified via `proxy_jump`. Fleet instances appear as normal instances, enabling you to run 
[dev environments](../../docs/concepts/dev-environments.md),
[tasks](../../docs/concepts/tasks.md), and [services](../../docs/concepts/services.md)
just as you would without `proxy_jump`.

<div class="termy">

```shell
$ dstack apply -f my-lambda-fleet.dstack.yml

Provisioning...
---> 100%

 FLEET            INSTANCE  RESOURCES      STATUS  CREATED 
 my-lambda-fleet  0         8xH100 (80GB)  idle    3 mins ago      
                  1         8xH100 (80GB)  idle    3 mins ago    
                  2         8xH100 (80GB)  idle    3 mins ago    
                  3         8xH100 (80GB)  idle    3 mins ago    
```

</div>

The `dstack` CLI automatically handles SSH tunneling and port forwarding when running workloads.

## What's next

To sum it up, the latest release enables `dstack` to be used efficiently not only with public clouds but also with private
clouds and data centers. It natively supports NVIDIA, AMD, Intel Gaudi, and soon other upcoming chips.

What’s also important is that `dstack` comes with a control plane that not only simplifies orchestration but also provides
a console for monitoring and managing workloads across projects (also known as tenants). 

As a container orchestrator, `dstack` remains a streamlined alternative to Kubernetes and Slurm for AI teams, focusing on
an AI-native experience, simplicity, and vendor-agnostic orchestration for both cloud and on-prem.

!!! info "Roadmap"
    We plan to further enhance `dstack`'s support for both cloud and on-premises setups. For more details on our roadmap,
    refer to our [GitHub :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/issues/2184){:target="_blank"}.

> Have questions? You're welcome to join
> our [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"} or talk
> directly to [our team :material-arrow-top-right-thin:{ .external }](https://calendly.com/dstackai/discovery-call){:target="_blank"}.
