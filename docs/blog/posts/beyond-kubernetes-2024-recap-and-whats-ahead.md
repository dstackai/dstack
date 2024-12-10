---
title: "Beyond Kubernetes: 2024 recap and what's next for AI infra"
date: 2024-12-10
description: "Reflecting on key milestones from 2024, and looking ahead to the next steps in simplifying AI infrastructure orchestration."  
slug: beyond-kubernetes-2024-recap-and-whats-ahead
image: https://github.com/dstackai/static-assets/blob/main/static-assets/images/beyond-kubernetes-2024-recap-and-whats-ahead.png?raw=true
categories:
  - AMD
  - NVIDIA
  - Volumes
  - Fleets
---

# Beyond Kubernetes: 2024 recap and what's ahead for AI infra 

At `dstack`, we are on a mission to simplify the development, training, and deployment of AI models, offering an
alternative to the complex Kubernetes ecosystem. Our goal is to help developers and organizations manage AI
infrastructure seamlessly across any cloud provider or accelerator chip—without vendor lock-in. 

As 2024 comes to a close, we reflect on the milestones we've achieved and look ahead to the next steps for both our
project and the broader AI infrastructure ecosystem.

<!-- more -->

## Ecosystem 

While `dstack` already integrates with leading cloud GPU providers, we are focused on expanding partnerships with
vendors who share our vision of simplifying AI infrastructure orchestration. Our aim is to provide developers and
organizations with a lightweight, efficient alternative to Kubernetes.

This year, we’re excited to welcome our first partners: [Lambda :material-arrow-top-right-thin:{ .external }](https://lambdalabs.com/){:target="_blank"}, 
[RunPod :material-arrow-top-right-thin:{ .external }](https://www.runpod.io/){:target="_blank"}, 
[CUDO Compute :material-arrow-top-right-thin:{ .external }](https://www.cudocompute.com/){:target="_blank"}, 
and [Hot Aisle :material-arrow-top-right-thin:{ .external }](https://hotaisle.xyz/){:target="_blank"}.

We’d also like to thank [Oracle  :material-arrow-top-right-thin:{ .external }](https://www.oracle.com/cloud/){:target="_blank"} 
for their collaboration, ensuring seamless integration between `dstack` and OCI.

> Special thanks to Lambda and Hot Aisle for providing NVIDIA and AMD hardware, which enabled us to conduct
[our benchmarks](/blog/category/benchmarks/). These benchmarks are essential for advancing the development of
> open-source inference and training stacks for all accelerator chips.

## Community

Thanks to your support, the project has reached [1.6K stars on GitHub :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack){:target="_blank"},
reflecting the interest and trust in its goals. 

Your feedback on [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"},
especially bug reports and feature requests, plays a critical role in the project's development.
As we move into the new year, we look forward to seeing more developers and teams supporting the project with feedback
and pull requests.


## Fleets

A key milestone for `dstack` this year has been the introduction of [fleets](/docs/concepts/fleets/), 
an abstraction that simplifies the management of clusters both in the cloud and on-prem.

### Cloud providers

Unlike Kubernetes, where node groups are typically managed through auto-scaling policies, `dstack` offers a more
streamlined approach to provisioning. With `dstack`, you simply define a fleet YAML file and run
`dstack apply`. This command automatically provisions clusters across any cloud provider.

For quick deployments, you can skip defining a fleet altogether. When you run a dev environment, task, or service,
`dstack` dynamically provisions a fleet. You still retain control over key settings, such as idle duration (the period a
fleet remains idle before `dstack` destroys it).

### On-prem server

Managing on-prem resources with `dstack` is equally straightforward. If you have SSH access to a group of hosts, simply
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

This transforms your on-prem cluster into a fully managed fleet, ready to run dev environments, tasks, and services,
with the same simplicity `dstack` offers for cloud fleets.

### GPU blocks

At `dstack`, when running a job on an instance—whether in the cloud or on-prem—uses all available GPUs on that
instance. In Q1 2025, we’re
introducing [GPU blocks :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/issues/1780){:target="_blank"},
enabling instances to allocate GPUs into discrete blocks that can be reused by concurrent jobs.

This feature enables more efficient use of expensive instances, driving improved resource management and 
cost optimization.

## Volumes

Another key milestone for `dstack` this year has been the introduction of [volumes](/docs/concepts/volumes), addressing a critical need in AI
infrastructure—data storage.

With `dstack`'s volumes, users can now leverage storage in both cloud and on-prem environments in a unified and efficient
manner.

## Accelerators

### NVIDIA

NVIDIA remains the top accelerator supported by `dstack`. Recently, we introduced a [NIM example](/examples/nim) 
for model deployment, and we continue to enhance support for NVIDIA’s AI stack.

### AMD

This year, we’re particularly proud of our expanded support for AMD, which is now available on both on-prem servers 
(with SSH fleets) and in the cloud.

> Currently, among cloud providers, [AMD :material-arrow-top-right-thin:{ .external }](https://www.amd.com/en/products/accelerators/instinct.html){:target="_blank"} is supported only through RunPod. In Q1 2025, we plan to extend it to
[Nscale :material-arrow-top-right-thin:{ .external }](https://www.nscale.com/){:target="_blank"}
> and potentially other providers open to collaboration.

### Intel

In Q1 2025, our roadmap includes extending `dstack`'s integration to new accelerators, including 
[Intel Gaudi :material-arrow-top-right-thin:{ .external }](https://www.intel.com/content/www/us/en/products/details/processors/ai-accelerators/gaudi-overview.html){:target="_blank"}
and potentially other chips.

## Join the community

If you're looking to simplify AI infrastructure, both in the cloud and on-prem, 
consider getting involved as a `dstack` user, open-source contributor, or ambassador.

We also welcome cloud, hardware, and software vendors to contribute to `dstack` and support 
its evolution as an open standard.