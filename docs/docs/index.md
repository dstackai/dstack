# What is dstack?

`dstack` is an open-source toolkit and orchestration engine for running GPU workloads. 
It works seamlessly with top cloud GPU providers (AWS, GCP, Azure, Lambda, TensorDock, Vast.ai, etc.)
as well as on-premises servers.

### Why use dstack?

1. Designed for development, training, and deployment of gen AI models.
2. Efficiently utilizes GPUs across regions and cloud providers.
3. Compatible with any frameworks.
4. 100% open-source.

### How does it work?

1. Install the open-source `dstack` server and configure cloud credentials (or opt for the cloud version.) 
2. Define run configurations such as dev environments, tasks, and services.
3. Execute configurations via the CLI or API. The `dstack` server automatically provisions cloud resources, handles 
   containers, logs, network, and everything else.

[//]: # (### Coming soon)

[//]: # (1. Multi-node tasks)
[//]: # (2. Auto-scalable services)
[//]: # (3. Integration with Kubernetes)

### Where do I start?

1. [Install the server](installation/index.md) (or <a href="https://cloud.dstack.ai">sign up</a> with the cloud version)
2. Follow [quickstart](quickstart.md)
3. Browse [examples](../examples/index.md)
4. Join the community via [Discord](https://discord.gg/u8SmfwPpMd)