# What is dstack?

`dstack` is an open-source container orchestrator that simplifies workload orchestration 
and drives GPU utilization for ML teams. It works with any GPU cloud, on-prem cluster, or accelerated hardware.

#### Accelerators

`dstack` supports `NVIDIA`, `AMD`, `TPU`, `Intel Gaudi`, and `Tenstorrent` accelerators out of the box.

## How does it work?

<img src="https://dstack.ai/static-assets/static-assets/images/dstack-architecture-diagram-v8.svg" />

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

!!! info "Where do I start?"
    1. Proceed to [installation](installation/index.md)
    2. See [quickstart](quickstart.md)
    3. Browse [examples](/examples)
    4. Join [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"}
