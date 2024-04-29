# What is dstack?

`dstack` is an open-source container orchestration engine designed for AI workloads across any cloud or data center.

> The supported cloud providers include AWS, GCP, Azure, Lambda, TensorDock, Vast.ai, CUDO, and RunPod.
> You can also use `dstack` ro run workloads on on-prem servers.

Think of `dstack` as a lightweight alternative to Kubernetes or Slurm that provides a
straightforward interface for AI model development, training, and deployment.

`dstack` supports dev environements, running tasks on clusters, and deployment with auto-scaling and built-in
authorization, all right out of the box.

`dstack` is vendor-agnostic, allowing you to utilize any open-source libraries, frameworks, or tools
from your container.

## Why use dstack?

1. Lightweight and easy-to-use compared to Kubernetes and Slurm
2. Supports all major GPU cloud providers
3. Scalable and reliable for production environments
4. Enables management of AI infrastructure across multiple clouds without vendor lock-in
5. Fully open-source

## How does it work?

1. [Install](installation/index.md) the open-source version of `dstack` and configure your own cloud accounts, or sign up with [dstack Sky :material-arrow-top-right-thin:{ .external }](https://sky.dstack.ai){:target="_blank"}
2. Define configurations such as [dev environments](concepts/dev-environments.md), [tasks](concepts/tasks.md), 
   and [services](concepts/services.md).
3. Run configurations via `dstack`'s CLI or API.
[//]: # (The `dstack` server automatically provisions cloud resources, handles containers, logs, network, and everything else.)
4. Use [pools](concepts/pools.md) to manage instances and on-prem servers.

[//]: # (### Coming soon)

[//]: # (1. Multi-node tasks)
[//]: # (2. Auto-scalable services)
[//]: # (3. Integration with Kubernetes)

## Where do I start?

1. Follow [quickstart](quickstart.md)
2. Browse [examples :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/README.md){:target="_blank"}
3. Join the community via [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"}