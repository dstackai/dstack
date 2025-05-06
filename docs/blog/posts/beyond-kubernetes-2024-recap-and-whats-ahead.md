---
title: "Beyond Kubernetes: 2024 recap and what's next for AI infra"
date: 2024-12-10
description: "Reflecting on key milestones from 2024, and looking ahead to the next steps in simplifying AI infrastructure orchestration."  
slug: beyond-kubernetes-2024-recap-and-whats-ahead
image: https://dstack.ai/static-assets/static-assets/images/beyond-kubernetes-2024-recap-and-whats-ahead.png
categories:
  - AMD
  - NVIDIA
  - Volumes
  - Cloud fleets
  - SSH fleets
---

# Beyond Kubernetes: 2024 recap and what's ahead for AI infra 

At `dstack`, we aim to simplify AI model development, training, and deployment of AI models by offering an
alternative to the complex Kubernetes ecosystem. Our goal is to enable seamless AI infrastructure management across any
cloud or hardware vendor. 

As 2024 comes to a close, we reflect on the milestones we've achieved and look ahead to the next steps.

<!-- more -->

## Ecosystem 

While `dstack` integrates with leading cloud GPU providers, we aim to expand partnerships with more providers 
sharing our vision of simplifying AI infrastructure orchestration with a lightweight, efficient alternative to Kubernetes.

This year, we’re excited to welcome our first partners: [Lambda :material-arrow-top-right-thin:{ .external }](https://lambdalabs.com/){:target="_blank"}, 
[RunPod :material-arrow-top-right-thin:{ .external }](https://www.runpod.io/){:target="_blank"}, 
[CUDO Compute :material-arrow-top-right-thin:{ .external }](https://www.cudocompute.com/){:target="_blank"}, 
and [Hot Aisle :material-arrow-top-right-thin:{ .external }](https://hotaisle.xyz/){:target="_blank"}.

We’d also like to thank [Oracle  :material-arrow-top-right-thin:{ .external }](https://www.oracle.com/cloud/){:target="_blank"} 
for their collaboration, ensuring seamless integration between `dstack` and OCI.

> Special thanks to [Lambda :material-arrow-top-right-thin:{ .external }](https://lambdalabs.com/){:target="_blank"} and
> [Hot Aisle :material-arrow-top-right-thin:{ .external }](https://hotaisle.xyz/){:target="_blank"} for providing NVIDIA and AMD hardware, enabling us conducting 
> [benchmarks](/blog/category/benchmarks/), which
> are essential to advancing open-source inference and training stacks for all accelerator chips.

## Community

Thanks to your support, the project has
reached [1.6K stars on GitHub :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack){:target="_blank"},
reflecting the growing interest and trust in its mission.
Your issues, pull requests, as well as feedback on [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"}, play a
critical role in the project's development.

## Fleets

A key milestone for `dstack` this year has been the introduction of [fleets](/docs/concepts/fleets/), 
an abstraction that simplifies the management of clusters.

### Cloud providers

Unlike Kubernetes, where node groups are typically managed through auto-scaling policies, `dstack` offers a more
streamlined approach. With `dstack`, you simply define a fleet YAML file and run
`dstack apply`. This command automatically provisions clusters across any cloud provider.

For quick deployments, you can skip defining a fleet altogether. When you run a dev environment, task, or service,
`dstack` creates a fleet automatically.

### On-prem server

Managing on-prem resources with `dstack`'s fleets is equally straightforward. If you have SSH access to a group of hosts, simply
list them in a YAML configuration file and run `dstack apply`.

<div editor-title="examples/misc/fleets/distrib-ssh.dstack.yml"> 

```yaml
type: fleet
# The name is optional, if not specified, generated randomly
name: my-fleet

# Ensure instances are inter-connected
placement: cluster

# The user, private SSH key, and hostnames of the on-prem servers
ssh_config:
  user: ubuntu
  identity_file: ~/.ssh/id_rsa
  hosts:
    - 3.255.177.51
    - 3.255.177.52
```

</div>

This turns your on-prem cluster into a `dstack` fleet, ready to run dev environments, tasks, and services.

### GPU blocks

At `dstack`, when running a job on an instance, it uses all available GPUs on that instance. In Q1 2025, we will
introduce [GPU blocks :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/issues/1780){:target="_blank"},
allowing the allocation of instance GPUs into discrete blocks that can be reused by concurrent jobs.

This will enable more cost-efficient utilization of expensive instances.

## Volumes

Another key milestone for `dstack` this year has been the introduction of [volumes](/docs/concepts/volumes), addressing
a critical need in AI infrastructure—data storage.

With `dstack`'s volumes, users can now leverage storage in both cloud and on-prem environments in a unified and
efficient manner.

## Accelerators

### NVIDIA

NVIDIA remains the top accelerator supported by `dstack`. Recently, we introduced a [NIM example](../../examples/deployment/nim/index.md) 
for model deployment, and we continue to enhance support for the rest of NVIDIA's ecosystem.

### AMD

This year, we’re particularly proud of our newly added integration with AMD.

`dstack` works seamlessly with any on-prem AMD clusters. For example, you can rent such servers through our partner 
[Hot Aisle :material-arrow-top-right-thin:{ .external }](https://hotaisle.xyz/){:target="_blank"}.

> Among cloud providers, [AMD :material-arrow-top-right-thin:{ .external }](https://www.amd.com/en/products/accelerators/instinct.html){:target="_blank"} is supported only through RunPod. In Q1 2025, we plan to extend it to
[Nscale :material-arrow-top-right-thin:{ .external }](https://www.nscale.com/){:target="_blank"},
> [Hot Aisle :material-arrow-top-right-thin:{ .external }](https://hotaisle.xyz/){:target="_blank"}, and potentially other providers open to collaboration.

### Intel

In Q1 2025, our roadmap includes added integration with 
[Intel Gaudi :material-arrow-top-right-thin:{ .external }](https://www.intel.com/content/www/us/en/products/details/processors/ai-accelerators/gaudi-overview.html){:target="_blank"}
among other accelerator chips.

## Join the community

If you're interested in simplifying AI infrastructure, both in the cloud and on-prem, consider getting involved as a 
`dstack` user, open-source contributor, or ambassador.

Finally, if you're a cloud, hardware, or software vendor, consider contributing to `dstack` and helping us drive it as
an open standard together.
