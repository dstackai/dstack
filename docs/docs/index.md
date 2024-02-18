# What is dstack?

`dstack` is an open-source engine for running GPU workloads on any cloud.
It works with a wide range of cloud GPU providers (AWS, GCP, Azure, Lambda, TensorDock, Vast.ai, etc.)
as well as on-premises servers.

### Why use dstack?

1. Designed for development, training, and deployment of gen AI models.
2. Efficiently utilizes GPUs across regions and cloud providers.
3. Compatible with any frameworks.
4. 100% open-source.

### How does it work?

1. [Install](installation/index.md) the open-source server and configure backends (or <a href="https://cloud.dstack.ai">sign up</a> with the cloud version) 
2. Define configurations such as dev environments, tasks, and services.
3. Run configurations via the CLI or API. The `dstack` server automatically provisions cloud resources, handles 
   containers, logs, network, and everything else.

[//]: # (### Coming soon)

[//]: # (1. Multi-node tasks)
[//]: # (2. Auto-scalable services)
[//]: # (3. Integration with Kubernetes)

### Where do I start?

1. Follow [quickstart](quickstart.md)
2. Browse [examples](../examples/index.md)
3. Join the community via [Discord](https://discord.gg/u8SmfwPpMd)