# What is dstack?

`dstack` is a streamlined alternative to Kubernetes, specifically designed for AI. It simplifies container orchestration
for AI workloads both in the cloud and on-prem, speeding up the development, training, and deployment of AI models.

`dstack` is easy to use with any cloud providers as well as on-prem servers. 

#### Accelerators

`dstack` supports `NVIDIA GPU`, `AMD GPU`, and `Google Cloud TPU` out of the box.

## How does it work?

> Before using `dstack`, ensure you've [installed](installation/index.md) the server, or signed up for [dstack Sky :material-arrow-top-right-thin:{ .external }](https://sky.dstack.ai){:target="_blank"}.

#### 1. Define configurations

`dstack` supports the following configurations:
   
* [Dev environments](dev-environments.md) &mdash; for interactive development using a desktop IDE
* [Tasks](tasks.md) &mdash; for scheduling jobs (incl. distributed jobs) or running web apps
* [Services](services.md) &mdash; for deployment of models and web apps (with auto-scaling and authorization)
* [Fleets](concepts/fleets.md) &mdash; for managing cloud and on-prem clusters
* [Volumes](concepts/volumes.md) &mdash; for managing persisted volumes
* [Gateways](concepts/volumes.md) &mdash; for configuring the ingress traffic and public endpoints

Configuration can be defined as YAML files within your repo.

#### 2. Apply configurations

Apply the configuration either via the `dstack apply` CLI command or through a programmatic API.

`dstack` automatically manages provisioning, job queuing, auto-scaling, networking, volumes, run failures,
out-of-capacity errors, port-forwarding, and more &mdash; across clouds and on-prem clusters.

## Why dstack?

`dstack`'s founder and CEO explains the challenges `dstack` addresses for AI and Ops teams.

<iframe width="700" height="394" src="https://www.youtube.com/embed/RIDMEutHuWo?si=6Quy34Kwj8wHvBTQ" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>

## Where do I start?

1. Proceed to [installation](installation/index.md)
2. See [quickstart](quickstart.md)
3. Browse [examples](/examples)
4. Join [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"}