# What is dstack?

`dstack` is a streamlined alternative to Kubernetes and Slurm, specifically designed for AI. It simplifies container orchestration
for AI workloads both in the cloud and on-prem, speeding up the development, training, and deployment of AI models.

`dstack` is easy to use with any cloud providers as well as on-prem servers. 

#### Accelerators

`dstack` supports `NVIDIA`, `AMD`, `TPU`, `Intel Gaudi`, and `Tenstorrent` accelerators out of the box.

## How does it work?

<img src="https://raw.githubusercontent.com/dstackai/static-assets/4aa9124edcaee397d9dd25d4b5aa8d8e82441852/static-assets/images/dstack-diagram.svg" />

#### 1. Set up the server

> Before using `dstack`, ensure you've [installed](installation/index.md) the server, or signed up for [dstack Sky :material-arrow-top-right-thin:{ .external }](https://sky.dstack.ai){:target="_blank"}.

#### 2. Define configurations

`dstack` supports the following configurations:
   
* [Dev environments](concepts/dev-environments.md) &mdash; for interactive development using a desktop IDE
* [Tasks](concepts/tasks.md) &mdash; for scheduling jobs, incl. distributed ones (or running web apps)
* [Services](concepts/services.md) &mdash; for deploying models (or web apps)
* [Fleets](concepts/fleets.md) &mdash; for managing cloud and on-prem clusters
* [Volumes](concepts/volumes.md) &mdash; for managing network volumes (to persist data)
* [Gateways](concepts/gateways.md) &mdash; for publishing services with a custom domain and HTTPS

Configuration can be defined as YAML files within your repo.

#### 3. Apply configurations

Apply the configuration either via the `dstack apply` CLI command (or through a programmatic API.)

`dstack` automatically manages infrastructure provisioning and job scheduling, while also handling auto-scaling,
port-forwarding, ingress, and more.

## Why dstack?

`dstack`'s founder and CEO explains the challenges `dstack` addresses for AI and Ops teams.

<iframe width="700" height="394" src="https://www.youtube.com/embed/yzVMp5Q0aPg?si=22QzF2OvtAybBWDg&rel=0" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>

`dstack` streamlines infrastructure management and container usage, enabling AI teams to work with any frameworks across
cloud platforms or on-premise servers.


[//]: # (??? info "Cloud platforms")
[//]: # (    TBA)

!!! info "Where do I start?"
    1. Proceed to [installation](installation/index.md)
    2. See [quickstart](quickstart.md)
    3. Browse [examples](/examples)
    4. Join [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"}
