# What is dstack?

`dstack` is an open-source container orchestration engine designed for running AI workloads across any cloud or data center.

> The supported cloud providers include AWS, GCP, Azure, Lambda, TensorDock, Vast.ai, CUDO, and RunPod.
> You can also use `dstack` ro run workloads on on-prem servers.

`dstack` supports dev environements, running tasks on clusters, and deployment with auto-scaling and
authorization out of the box.

## Why use dstack?

1. Simplifies development, training, and deployment of AI
2. Supports major GPU cloud providers as well as on-prem servers
3. Leverages the open-source AI ecosystem of libraries, frameworks, and models
4. Reduces GPU costs and improves workload efficiency
5. Allows the use of multiple cloud providers

## How does it work?

1. [Install](installation/index.md) the open-source version of `dstack` and configure your own cloud accounts, or sign up with [dstack Sky :material-arrow-top-right-thin:{ .external }](https://sky.dstack.ai){:target="_blank"}
2. Define configurations such as [dev environments](concepts/dev-environments.md), [tasks](concepts/tasks.md), 
   and [services](concepts/services.md).
3. Run configurations via `dstack`'s CLI or API.
4. Use [pools](concepts/pools.md) to manage cloud instances and on-prem servers.

## Where do I start?

1. Follow [quickstart](quickstart.md)
2. Browse [examples :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/tree/master/examples){:target="_blank"}
3. Join the community via [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"}