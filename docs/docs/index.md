# What is dstack?

`dstack` is an open-source container orchestration engine for running AI workloads across diverse cloud providers
and on-premises data centers. It simplifies provisioning compute resources, managing dev environments, executing tasks on clusters, and deploying services.

!!! info "Cloud and on-premises"
    `dstack` allows workload orchestration on both cloud and on-premises clusters.
    Supported cloud providers include AWS, GCP, Azure, OCI, Lambda, TensorDock, Vast.ai, RunPod, and CUDO.

!!! info "Accelerators"
    `dstack` supports NVIDIA GPUs and Google Cloud TPUs out of the box.

## How does it work?

!!! info "Installation"
    Before using `dstack`, [install](installation/index.md) the `dstack` server and configure credentials
    and other settings for each cloud account that you intend to use.

#### 1. Define configurations

`dstack` supports three types of run configurations:
   
* [`dev environment`](concepts/dev-environments.md) &mdash; for interactive development using a desktop IDE
* [`task`](concepts/tasks.md) &mdash; for any kind of batch jobs or web applications (supports distributed jobs)
* [`service`](concepts/services.md)&mdash; for production-grade deployment (supports auto-scaling and authorization)

Each type of run configuration allows you to specify commands for execution, required compute resources, retry policies, auto-scaling rules, authorization settings, and more.

Configuration can be defined as YAML files within your repo.

#### 2. Run configurations

Run any defined configuration either via `dstack` CLI or API.
   
`dstack` automatically provisions compute resources (whether from the cloud or on-premises), executes commands, handles interruptions, port-forwarding, auto-scaling, network, volumes, run failures, out-of-capacity errors, and more.

#### 3. Manage pools

Use [pools](concepts/pools.md) to manage the lifecycle of cloud instances and add/remove on-prem clusters.
   
You can manually add or remove cloud instances from the pool, or have them provisioned on-demand and configure how long they remain idle before automatic termination.


## Where do I start?

1. Proceed to [installation](installation/index.md)
2. See [quickstart](quickstart.md)
3. Browse [examples :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/tree/master/examples){:target="_blank"}
4. Join [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"}