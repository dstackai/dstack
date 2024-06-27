# What is dstack?

`dstack` is a robust, open-source container orchestration engine for running AI workloads across diverse cloud platforms
and on-premises data centers.
It streamlines the management of dev environments, task execution on clusters, and deployment.

> Compatible with any cloud provider, including AWS, GCP, Azure, OCI, Lambda, TensorDock, Vast.ai, RunPod, and CUDO, as
> well as on-premises clusters.
>
> Offers native support for NVIDIA GPU and Google Cloud TPU accelerator chips.

## Why use dstack?

1. Simplifies the development, training, and deployment for AI teams
2. Operates seamlessly with any cloud provider and data center
3. Easily integrates with any open-source training or serving frameworks
4. Reduces compute costs while enhancing workload efficiency
5. Provides a more AI-centric and simplified alternative to Kubernetes

## How does it work?

!!! info "Installation"
    Before using `dstack`, either set up the open-source server, or sign up
    with `dstack Sky`.
    See [Installation](installation/index.md) for more details.

1. Define configurations such as [dev environments](concepts/dev-environments.md), [tasks](concepts/tasks.md), 
   and [services](concepts/services.md).
2. Run configurations via `dstack`'s CLI or API.
3. Use [pools](concepts/pools.md) to manage cloud instances and on-prem clusters.

## Where do I start?

1. Proceed to [installation](installation/index.md)
2. See [quickstart](quickstart.md)
3. Browse [examples :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/tree/master/examples){:target="_blank"}
4. Join [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"}