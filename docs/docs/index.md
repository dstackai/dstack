# What is dstack?

`dstack` is an open-source orchestration engine for running AI workloads. It supports a wide range of cloud providers (such as AWS, GCP, Azure,
Lambda, TensorDock, Vast.ai, CUDO, RunPod, etc.) as well as on-premises infrastructure.

## Why use dstack?

1. Designed for development, training, and deployment of gen AI models.
2. Efficiently utilizes compute across cloud providers and on-prem servers.
3. Compatible with any training, fine-tuning, and serving frameworks, as well as other third-party tools.
4. 100% open-source.

## How does it work?

1. [Install](installation/index.md) the open-source version of `dstack` and configure your own cloud accounts, or sign up with [dstack Sky](https://sky.dstack.ai) 
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
2. Browse [examples](../examples/index.md)
3. Join the community via [Discord](https://discord.gg/u8SmfwPpMd)