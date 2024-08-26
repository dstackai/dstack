# What is dstack?

`dstack` is a lightweight alternative to Kubernetes, designed specifically for managing the development, training, and
deployment of AI models at any scale.

`dstack` is easy to use with any cloud provider (AWS, GCP, Azure, OCI, Lambda, TensorDock, Vast.ai, RunPod, etc.) or
any on-prem clusters.

If you already use Kubernetes, `dstack` can be used with it.

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

## Where do I start?

1. Proceed to [installation](installation/index.md)
2. See [quickstart](quickstart.md)
3. Browse [examples](/examples)
4. Join [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"}