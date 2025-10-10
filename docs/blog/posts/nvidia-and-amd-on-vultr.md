---
title: Supporting NVIDIA and AMD accelerators on Vultr
date: 2025-02-17
description: "Introducing integration with Vultr: The new integration allows Vultr customers to train and deploy models on both AMD and NVIDIA GPUs."  
slug: nvidia-and-amd-on-vultr
image: https://dstack.ai/static-assets/static-assets/images/dstack-vultr.png
categories:
  - Changelog
---

# Supporting NVIDIA and AMD accelerators on Vultr

As demand for AI infrastructure grows, the need for efficient, vendor-neutral orchestration tools is becoming
increasingly important.
At `dstack`, we’re committed to redefining AI container orchestration by prioritizing an AI-native, open-source-first
approach.
Today, we’re excited to share a new integration and partnership
with [Vultr :material-arrow-top-right-thin:{ .external }](https://www.vultr.com/){:target="_blank"}.

<img src="https://dstack.ai/static-assets/static-assets/images/dstack-vultr.png" width="630"/>

This new integration enables Vultr customers to train and deploy models on both AMD
and NVIDIA GPUs with greater flexibility and efficiency–using `dstack`. 

<!-- more -->

## About Vultr

[Vultr :material-arrow-top-right-thin:{ .external }](https://www.vultr.com/){:target="_blank"} provides cloud GPUs across 32 regions, supporting both NVIDIA and AMD hardware with on-demand and reserved
capacity. Their offerings include AMD MI300X and NVIDIA GH200, H200, H100, A100, L40S, and A40, all available at
competitive [pricing :material-arrow-top-right-thin:{ .external }](https://www.vultr.com/pricing/#cloud-gpu){:target="_blank"}.

## Why dstack

Kubernetes wasn’t built for AI. It’s powerful, but it adds unnecessary complexity that slows down development, training,
and deployment. That’s where `dstack` comes in.

`dstack` is an open-source orchestrator designed specifically for AI. Here’s a quick look at how it simplifies running dev
environments and services on Vultr:

<iframe width="700" height="394" src="https://www.youtube.com/embed/WnmP2zbUh7w?si=6bIcPifxD3BEVp3I&rel=0" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>

`dstack` runs on any cloud or on-prem setup, providing a simple way to manage dev environments, tasks, services, fleets,
and volumes—so you can focus on building instead of troubleshooting infrastructure.

## Getting started

To use `dstack` with your Vultr account, you need to [configure a `vultr` backend](../../docs/concepts/backends.md):

Log into your [Vultr :material-arrow-top-right-thin:{ .external }](https://www.vultr.com/) account, click `Account` in the sidebar, select `API`, find the `Personal Access Token` panel and click the `Enable API` button. In the `Access Control` panel, allow API requests from all addresses or from the subnet where your `dstack` server is deployed.

Then, go ahead and configure the backend:

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
  - name: main
    backends:
      - type: vultr
        creds:
          type: api_key
          api_key: B57487240a466624b48de22865589
```

</div>

For more details, refer to [Installation](../../docs/installation/index.md).

> Interested in fine-tuning or deploying DeepSeek on Vultr? Check out the corresponding [example](../../examples/llms/deepseek/index.md).

!!! info "What's next?"
    1. Refer to [Quickstart](../../docs/quickstart.md)
    2. Sign up with [Vultr :material-arrow-top-right-thin:{ .external }](https://www.vultr.com/)
    3. Check [dev environments](../../docs/concepts/dev-environments.md), 
        [tasks](../../docs/concepts/tasks.md), [services](../../docs/concepts/services.md), 
        and [fleets](../../docs/concepts/fleets.md)
    4. Join [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"}
