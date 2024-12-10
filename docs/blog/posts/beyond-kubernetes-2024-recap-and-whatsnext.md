---
title: "Beyond Kubernetes: 2024 recap and what's next for AI infra"
date: 2024-12-10
description: "Reflecting on key milestones from 2024, and looking ahead to the next steps in simplifying AI infrastructure orchestration."  
slug: beyond-kubernetes-2024-recap-and-whatsnext
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
for their collaboration, which helped ensure that `dstack` is fully compatible with Oracle's GPUs.

> Special thanks to Lambda and Hot Aisle for providing NVIDIA and AMD hardware, which enabled us to conduct
[our benchmarks](/blog/category/benchmarks/). These benchmarks are essential for advancing the development of
> open-source inference and training stacks for all accelerator chips.

As `dstack` continues to build an open standard, we encourage cloud and hardware vendors to contribute to the project. 

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

!!! info "GPU blocks"
    Currently, if `dstack` runs a job on an instance, it uses all of its GPUs. In the upcoming update, we’ll allow configuring
    the number of concurrent jobs per instance, enabling jobs to use only a fraction of the available GPUs, improving
    cost-effective utilization of expensive hardware.

## Volumes

A key milestone for `dstack` this year has been the introduction of [volumes](/docs/concepts/volumes), addressing a critical need in AI
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

> Currently, among cloud providers, AMD is supported only through RunPod. In Q1 2025, we plan to extend it to
[Nscale :material-arrow-top-right-thin:{ .external }](https://www.nscale.com/){:target="_blank"}
> and potentially other providers open to collaboration.

### Others

As AI infrastructure demand continues to grow, we plan to enhance `dstack`'s support for GCP’s TPU and expand
integration with additional accelerator chips, including AWS’s Inferentia/Trainium, Intel’s Gaudi, and potentially more.