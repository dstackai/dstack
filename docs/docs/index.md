# What is dstack?

`dstack` is a streamlined alternative to Kubernetes and Slurm, specifically designed for AI. It simplifies container orchestration
for AI workloads both in the cloud and on-prem, speeding up the development, training, and deployment of AI models.

`dstack` is easy to use with any cloud providers as well as on-prem servers. 

#### Accelerators

`dstack` supports `NVIDIA GPU`, `AMD GPU`, and `Google Cloud TPU` out of the box.

## How does it work?

![](https://raw.githubusercontent.com/dstackai/static-assets/refs/heads/main/static-assets/images/dstack-architecture-diagram.svg)

#### 1. Set up the server

> Before using `dstack`, ensure you've [installed](installation/index.md) the server, or signed up for [dstack Sky :material-arrow-top-right-thin:{ .external }](https://sky.dstack.ai){:target="_blank"}.

#### 2. Define configurations

`dstack` supports the following configurations:
   
* [Dev environments](dev-environments.md) &mdash; for interactive development using a desktop IDE
* [Tasks](tasks.md) &mdash; for scheduling jobs, incl. distributed ones (or running web apps)
* [Services](services.md) &mdash; for deploying models (or web apps)
* [Fleets](concepts/fleets.md) &mdash; for managing cloud and on-prem clusters
* [Volumes](concepts/volumes.md) &mdash; for managing network volumes (to persist data)
* [Gateways](concepts/gateways.md) &mdash; for publishing services with a custom domain and HTTPS

Configuration can be defined as YAML files within your repo.

#### 3. Apply configurations

Apply the configuration either via the `dstack apply` CLI command (or through a programmatic API.)

`dstack` automatically manages infrastructure provisioning and job scheduling, while also handling auto-scaling,
port-forwarding, ingress, and more.

## Why dstack?

`dstack`'s founder and CEO explains the challenges `dstack` addresses for AI and Ops teams.

<iframe width="700" height="394" src="https://www.youtube.com/embed/yzVMp5Q0aPg?si=22QzF2OvtAybBWDg&rel=0" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>

`dstack` streamlines infrastructure management and container usage, enabling AI teams to work with any frameworks across
cloud platforms or on-premise servers.

## How does it compare to other tools?

??? info "Kubernetes"
    #### How does dstack compare to Kubernetes? 
    
    `dstack` and Kubernetes are both container orchestrators for cloud and on-premises environments.

    However, `dstack` is more lightweight, and is designed specifically for AI, enabling AI engineers to handle development, training, and 
    deployment without needing extra tools or Ops support. 

    With `dstack`, you don't need Kubeflow or other ML platforms on top—everything is available out of the box.

    Additionally, `dstack` is much easier to use for on-premises servers—just provide hostnames and SSH credentials, 
    and `dstack` will automatically create a fleet ready for use with development environments, tasks, and services.

    #### How does dstack compare to KubeFlow? 
    `dstack` can be used entirely instead of Kubeflow. It covers everything that Kubeflow does, and much more on top, 
    including development environments, services, and additional features.

    `dstack` is easier to set up with on-premises servers, doesn't require Kubernetes, and works with multiple cloud 
    providers out of the box.

    #### Can dstack and Kubernetes be used together?

    For AI development, it’s more efficient to use `dstack` directly with your cloud accounts or on-prem servers&mdash;without Kubernetes.

    However, if you prefer, you can set up the `dstack` server with a Kubernetes backend to provision through Kubernetes.

    Does your Ops team insist on using Kubernetes for production-grade deployment? You can use `dstack` and
    Kubernetes side by side; `dstack` for development and Kubernetes for production-grade deployment.

??? info "Slurm"
    #### How does dstack compare to Slurm?
    `dstack` can be used entirely instead of Slurm. It covers everything that Slurm does, and a lot more on top, including
    dev environments, services, out-of-the-box cloud support, easier setup with on-premises servers, and much more.

[//]: # (??? info "Cloud platforms")
[//]: # (    TBA)

## Where do I start?

1. Proceed to [installation](installation/index.md)
2. See [quickstart](quickstart.md)
3. Browse [examples](/examples)
4. Join [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"}