# What is dstack?

`dstack` is an open-source container orchestration engine for running AI workloads across diverse cloud providers
and on-premises data centers. It simplifies provisioning compute resources, managing dev environments, executing tasks on clusters, and deploying services.

!!! info "Supported clouds"
    `dstack` supports many cloud providers including AWS, GCP, Azure, OCI, Lambda, TensorDock, Vast.ai, RunPod, and CUDO, as well as on-premises clusters.

!!! info "Supported accelerators"
    `dstack` offers native support for NVIDIA GPU and Google Cloud TPU chips.

## Why use dstack?

1. Simplifies the development, training, and deployment for AI teams
2. Operates seamlessly with any cloud provider and data center
3. Easily integrates with any open-source training or serving frameworks
4. Reduces compute costs while enhancing workload efficiency
5. Provides a more AI-centric and simplified alternative to Kubernetes

## How does it work?

1. [Install](installation/index.md) `dstack`.
   Configure the open-source server or sign up with [`dstack Sky`](https://sky.dstack.ai/).
   With the open-source option, you host the server and bring your cloud credentials.
   With `dstack Sky`, the server is managed for you and you can run on any cloud without setting up an account for each.
2. Define configurations such as [dev environments](concepts/dev-environments.md), [tasks](concepts/tasks.md), 
   and [services](concepts/services.md).
   `dstack` offers three types of configurations optimized for development, batch jobs, and service deployment.
   You can configure commands to execute, required compute resources, retry policy, autoscaling, authorization and more.
2. Run configurations via `dstack`'s CLI or API.
   `dstack` will provision the best compute offer on the market that meets the requirements,
   be it a GPU cluster or a CPU instance, and execute the configuration commands.
   With retry enabled, `dstack` can handle no capacity situations, spot interruptions, and run failures.
3. Use [pools](concepts/pools.md) to manage cloud instances and on-prem clusters.
   `dstack` gives you the control to terminate instances as soon as runs finish or keep them in a pool
    to save on provisioning time and guarantee compute availability.

## Where do I start?

1. Proceed to [installation](installation/index.md)
2. See [quickstart](quickstart.md)
3. Browse [examples :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/tree/master/examples){:target="_blank"}
4. Join [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"}