---
title: What is dstack?
description: Introduction to dstack and how it works
---

# What is dstack?

`dstack` is a unified control plane for GPU provisioning and orchestration that works with any GPU cloud, Kubernetes, or on-prem clusters. 

It streamlines development, training, and inference, and is compatible with any hardware, open-source tools, and frameworks.

!!! info "Accelerators"
    `dstack` supports `NVIDIA`, `AMD`, `TPU`, and `Tenstorrent` accelerators out of the box.

## How does it work?

<!-- Architecture diagram — prebuilt light/dark SVG pair shared with the landing
     (website/src/components/ArchitectureDiagram.tsx) and the README, served from the
     dstackai/static-assets repo. The files are self-contained (embedded fonts + logos);
     the pair swaps with the docs theme via .arch-svg in
     mkdocs/assets/stylesheets/cloudscape-docs.css. -->
<img class="arch-svg arch-svg--light" src="https://dstack.ai/static-assets/static-assets/images/dstack-architecture-diagram.svg" alt="dstack architecture: an orchestration layer between AI frameworks and models on top, and GPU clouds, Kubernetes, VMs, bare-metal, and hardware below.">
<img class="arch-svg arch-svg--dark" src="https://dstack.ai/static-assets/static-assets/images/dstack-architecture-diagram-dark.svg" alt="dstack architecture: an orchestration layer between AI frameworks and models on top, and GPU clouds, Kubernetes, VMs, bare-metal, and hardware below.">

### Set up the server

> Before using `dstack`, ensure you've [installed](installation.md) the server, or signed up for [dstack Sky](https://sky.dstack.ai).

### Define configurations

`dstack` supports the following configurations:
   
* [Fleets](concepts/fleets.md) &mdash; Provision and manage clusters across clouds, Kubernetes, and on-prem
* [Dev environments](concepts/dev-environments.md) &mdash; Launch dev environments to be accessed by agents or from your IDE
* [Tasks](concepts/tasks.md) &mdash; Run training, batch or other jobs across a single node or clusters
* [Services](concepts/services.md) &mdash; Deploy model inference as secure and scalable endpoints
* [Presets](concepts/presets.md) &mdash; Agent-driven inference optimization (experimental)
* [Volumes](concepts/volumes.md) &mdash; Managing instance and network volumes for persisting data

Configuration can be defined as YAML files within your repo.

### Apply configurations

Apply the configuration either via the `dstack apply` CLI command (or through a programmatic API.)

`dstack` automatically manages infrastructure provisioning and job scheduling, while also handling auto-scaling,
port-forwarding, ingress, and more.

!!! info "Where do I start?"
    1. Proceed to [installation](installation.md)
    2. See [quickstart](quickstart.md)
    3. Browse [examples](/examples)
    4. Join [Discord](https://discord.gg/u8SmfwPpMd)
