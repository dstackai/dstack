# What is dstack?

`dstack` is an open-source container orchestration engine designed for running AI workloads across any cloud or data center.

> The supported cloud providers include AWS, GCP, Azure, OCI, Lambda, TensorDock, Vast.ai, RunPod, and CUDO.
> You can also use `dstack` ro run workloads on on-prem servers.

`dstack` supports dev environements, running tasks on clusters, and deployment with auto-scaling and
authorization out of the box.

## Why use dstack?

1. Simplifies development, training, and deployment of AI
2. Can be used with any cloud providers and data centers
3. Leverages the open-source AI ecosystem of libraries, frameworks, and models
4. Reduces GPU costs and improves workload efficiency

## How does it work?

!!! info "Installation"
    Before using `dstack`, either set up the open-source server, or sign up
    with [dstack Sky :material-arrow-top-right-thin:{ .external }](https://sky.dstack.ai){:target="_blank"}.
    See [Installation](installation/index.md) for more details.

1. Define configurations such as [dev environments](concepts/dev-environments.md), [tasks](concepts/tasks.md), 
   and [services](concepts/services.md).
2. Run configurations via `dstack`'s CLI or API.
3. Use [pools](concepts/pools.md) to manage cloud instances and on-prem servers.

## Where do I start?

1. Proceed to [installation](installation/index.md)
2. See [quickstart](quickstart.md)
3. Browse [examples :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/tree/master/examples){:target="_blank"}
4. Join [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"}