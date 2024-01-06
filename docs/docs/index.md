# What is dstack?

`dstack` is an open-source toolkit for running GPU workloads 
on any cloud. It works seamlessly with top cloud GPU providers (AWS, GCP, Azure, Lambda, TensorDock, Vast.ai, etc.)

### Why use dstack?

1. Designed for development, training, and deployment of gen AI models.
2. Efficiently utilizes GPUs across regions and cloud providers.
3. Compatible with any frameworks.
4. 100% open-source.

### How does it work?

1. Set up the open-source `dstack` server and configure cloud credentials (or opt for the cloud version.) 
2. Define run configurations using YAML (supports development, training, and deployment).
3. Execute configurations via CLI. The `dstack` server automatically provisions cloud resources, handles 
   containers, logs, network, and everything else needed to run workloads.

[//]: # (### Coming soon)

[//]: # (1. Multi-node tasks)
[//]: # (2. Auto-scalable services)
[//]: # (3. Integration with Kubernetes)

### Where do I start?

1. [Install the server](installation/index.md) (or <a href="#" data-tally-open="w7K17R">sign up</a> with the cloud version)
2. Follow [quickstart](quickstart.md)
3. Browse [examples](../../examples/index.md)
4. Join the community via [Discord](https://discord.gg/u8SmfwPpMd)