# What is dstack?

`dstack` is an open-source container orchestration engine for AI. 
It accelerates the development, training, and deployment of AI models, and simplifies the management of clusters.

#### Cloud and on-prem

`dstack` is easy to use with any cloud or on-prem servers.
Supported cloud providers include AWS, GCP, Azure, OCI, Lambda, TensorDock, Vast.ai, RunPod, and CUDO.
For using `dstack` with on-prem servers, see [fleets](fleets.md#__tabbed_1_2).

#### Accelerators

`dstack` supports `NVIDIA GPU` and `Google Cloud TPU` out of the box.

## How does it work?

> Before using `dstack`, [install](installation/index.md) the server and configure 
backends for each cloud account (or Kubernetes cluster) that you intend to use.

#### 1. Define run configurations

`dstack` supports three types of run configurations:
   
* [Dev environments](dev-environments.md) &mdash; for interactive development using a desktop IDE
* [Tasks](tasks.md) &mdash; for any kind of batch jobs or web applications (supports distributed jobs)
* [Services](services.md)&mdash; for production-grade deployment (supports auto-scaling and authorization)

Each type of run configuration allows you to specify commands for execution, required compute resources, retry policies, auto-scaling rules, authorization settings, and more.

Configuration can be defined as YAML files within your repo.

#### 2. Run configurations

Run any defined configuration either via `dstack` CLI or API.
   
`dstack` automatically handles provisioning, interruptions, port-forwarding, auto-scaling, network, volumes, 
run failures, out-of-capacity errors, and more.

#### 3. Manage fleets

Use [fleets](fleets.md) to provision and manage clusters and instances, both in the cloud and on-prem.

## Where do I start?

1. Proceed to [installation](installation/index.md)
2. See [quickstart](quickstart.md)
3. Browse [examples :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/tree/master/examples){:target="_blank"}
4. Join [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"}