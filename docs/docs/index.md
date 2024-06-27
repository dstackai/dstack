# What is dstack?

`dstack` is an open-source container orchestration engine designed for running AI workloads across any cloud or data center.
It simplifies dev environments, running tasks on clusters, and deployment.

> `dstack` is easy to use with any cloud provider (e.g. AWS, GCP, Azure, OCI, Lambda, TensorDock, Vast.ai, RunPod, CUDO, etc.)
> as well as on-prem clusters.
>
> `dstack` natively supports NVIDIA GPU, and Google Cloud TPU accelerator chips.

## Why use dstack?

1. Simplifies development, training, and deployment for AI teams
2. Can be used with any cloud providers and data centers
3. Very easy to use with any training or serving open-source frameworks
4. Reduces compute costs and improves workload efficiency
5. Much simpler compared to Kubernetes

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