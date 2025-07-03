---
title: "Case study: how EA uses dstack to fast-track AI development"
date: 2025-05-22
description: "TBA"  
slug: ea-gtc25
image: https://dstack.ai/static-assets/static-assets/images/dstack-ea-slide-2-background-min.png
categories:
  - Case studies
links:
  - NVIDIA GTC 2025 ↗: https://www.nvidia.com/en-us/on-demand/session/gtc25-s73667/
---

# How EA uses dstack to fast-track AI development

At NVIDIA GTC 2025, Electronic Arts [shared :material-arrow-top-right-thin:{ .external }](https://www.nvidia.com/en-us/on-demand/session/gtc25-s73667/){:target="_blank"} how they’re scaling AI development and managing infrastructure across teams. They highlighted using tools like `dstack` to provision GPUs quickly, flexibly, and cost-efficiently. This case study summarizes key insights from their talk.

<img src="https://dstack.ai/static-assets/static-assets/images/dstack-ea-slide-1.png" width="630" />

EA has over 100+ AI projects running, and the number keeps growing. There are many teams with AI needs—game dev, ML engineers, AI researchers, and platform teams—supported by a central tech team. Some need full MLOps support; others have in-house expertise but need flexible tooling and infrastructure.

<!-- more -->

The central tech team ensures all teams have what they require, including tools, infrastructure, and expertise.

<!-- <img src="https://dstack.ai/static-assets/static-assets/images/dstack-ea-slide-1-1.png" width="630" style="border: 0.5px dotted black"/> -->

As EA’s AI efforts grew, they faced major challenges:

* **Tool fragmentation**: Teams used different tools and workflows, leading to duplicated effort and poor collaboration.  
* **High GPU costs**: Spinning up GPUs could take days or weeks. To avoid delays, teams often left machines running idle, increasing costs.  
* **Heavy engineering burden**: ML engineers spent time managing infrastructure—setting up clusters, configuring environments, and deploying models—instead of building AI.

The typical AI workflow at EA includes:

1. Development and training  
2. Model storage and distribution  
3. Serving and scaling

Each stage comes with scaling challenges, from GPU compute provisioning efficiency to fragmented tooling and complex project setups.

<img src="https://dstack.ai/static-assets/static-assets/images/dstack-ea-slide-2.png" width="630" style="border: 0.5px dotted black"/>

EA's centralized approach uses these core ML tools:

* `dstack` – for provisioning compute for AI workloads at scale, covering everything related to ML development and training  
* ML Artifactory – for managing  artifacts at scale  
* AXS (Kubernetes+) – for scalable inference and production serving

EA uses `dstack` to streamline GPU provisioning and AI workflow orchestration. It's open-source, cloud-agnostic, automated, and integrates seamlessly with teams' existing dev workflows.

<!-- In addition to the cloud-agnostic interface for ML teams, dstack eliminates the need for filing infra tickets and waiting days or weeks to get a GPU box or cluster, it just spins up what you need in minutes. -->

> *Because our teams are fragmented, we want them to be able to run on any environment of their choosing... It has to work with all of these. That means a centralized, unified interface to talk to all of them.*
>
> *— Wah Loon Keng, Sr. AI Engineer, Electronic Arts*

EA teams use `dstack` for three types of ML workloads:

* [Dev environments](../../docs/concepts/dev-environments.md): spining up GPU boxes pre-setup with a Gitrepo, and ready to use via desktop IDE such as VS Code, Cursor, etc  
* [Tasks](../../docs/concepts/tasks.md): seamless single-node or distributed training using open-source PyTorch libraries  
* [Services](../../docs/concepts/services.md): running model endpoints and Streamlit-style apps for quick internal demos and prototyping

Introducing `dstack` had a significant impact on EA’s ML teams. Before, getting access to GPU infrastructure could take days or even weeks. With dstack, teams can now spin up what they need in just minutes. This shift accelerated development by removing delays and freeing engineers to focus on building models.

> *With dstack, what used to take weeks,  provisioning GPUs, setting up environments, now takes minutes. It changed how fast teams at EA can move.*
>
> *— Wah Loon Keng, Sr. AI Engineer, Electronic Arts*

Costs dropped by nearly a factor of three, largely due to dstack’s ability to automatically start and stop resources using spot and on-demand instances.

<img src="https://dstack.ai/static-assets/static-assets/images/dstack-ea-slide-3.png" width="630" />

Workflows became standardized, reproducible, and easier to trace—thanks to the use of version-controlled YAML configurations. Teams across different departments and cloud providers now follow the same setup and processes.

> `dstack` provisions compute on demand and automatically shuts it down when no longer needed. That alone saves you over three times in cost.”
>
> — Wah Loon Keng, Sr. AI Engineer, Electronic Arts

<!-- EA’s experience highlights how critical standardized, open-source tooling is for scaling AI across teams. Instead of each group reinventing infrastructure and workflows, they’ve moved toward a common stack that supports fast iteration, reproducibility, and cost-efficient use of compute.  -->

By adopting tools that are cloud-agnostic and developer-friendly, EA has reduced friction—from provisioning GPUs to deploying models—and enabled teams to spend more time on actual ML work.

*Huge thanks to Kris and Keng from EA’s central tech team for sharing these insights. For more details, including the recording and slides, check out the full talk on the [NVIDIA GTC website :material-arrow-top-right-thin:{ .external }](https://www.nvidia.com/en-us/on-demand/session/gtc25-s73667/){:target="_blank"}.*

!!! info "What's next?"
    1. Check [dev environments](../../docs/concepts/dev-environments.md), [tasks](../../docs/concepts/tasks.md), [services](../../docs/concepts/services.md), and [fleets](../../docs/concepts/fleets.md)
    2. Follow [Quickstart](../../docs/quickstart.md)
    3. Browse [Examples](../../examples.md)
