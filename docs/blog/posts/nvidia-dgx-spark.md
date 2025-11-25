---
title: "Orchestrating workloads on NVIDIA DGX Spark"
date: 2025-11-14
description: "TBA"
slug: nvidia-dgx-spark
image: https://dstack.ai/static-assets/static-assets/images/nvidia-dgx-spark.png
# categories:
#   - Benchmarks
---

# Orchestrating workloads on NVIDIA DGX Spark

With support from [Graphsignal](https://x.com/GraphsignalAI/status/1986565583593197885), our team gained access to the new [NVIDIA DGX Spark](https://www.nvidia.com/en-us/products/workstations/dgx-spark/) and used it to validate how `dstack` operates on this hardware. This post walks through how to set it up with `dstack` and use it alongside existing on-prem clusters or GPU cloud environments to run workloads.

<img src="https://dstack.ai/static-assets/static-assets/images/nvidia-dgx-spark.png" width="630"/>

<!-- more -->

If DGX Spark is new to you, here is a quick breakdown of the key specs.

* Built on the NVIDIA GB10 Grace Blackwell Superchip with Arm CPUs.
* Capable of up to 1 petaflop of AI compute at FP4 precision, roughly comparable to RTX 5070 performance.
* Features 128GB of unified CPU and GPU memory enabled by the Grace Blackwell architecture.
* Ships with NVIDIA DGX OS (a tuned Ubuntu build) and NVIDIA Container Toolkit.

These characteristics make DGX Spark a fitting extension for local development and smaller-scale model training or inference, including workloads up to the GPT-OSS 120B range.

## Creating an SSH fleet

Because DGX Spark supports SSH and containers, integrating it with dstack is straightforward. Start by configuring an [SSH fleet](../../docs/concepts/fleets.md#ssh-fleets). The file needs the hosts and access credentials.

<div editor-title="fleet.dstack.yml">

```yaml
type: fleet
name: spark

ssh_config:
  user: devops
  identity_file: ~/.ssh/id_rsa
  hosts:
    - spark-e3a4
```

</div>

The `user` must have `sudo` privileges.

Apply the configuration:

<div class="termy">

```shell
$ dstack apply -f fleet.dstack.yml

Provisioning...
---> 100%

 FLEET  INSTANCE  GPU     PRICE  STATUS  CREATED 
 spark  0         GB10:1  $0     idle    3 mins ago      
```

</div>

Once active, the system detects hardware and marks the instance as `idle`. From here, you can run
[dev environments](../../docs/concepts/dev-environments.md), [tasks](../../docs/concepts/tasks.md), 
and [services](../../docs/concepts/services.md) on the DGX Spark fleet, the same way you would with other on-prem or cloud GPU backends.

## Running a dev environment

Example configuration:

<div editor-title=".dstack.yml">

```yaml
type: dev-environment
name: cursor

image: lmsysorg/sglang:spark

ide: cursor

resources:
  gpu: GB10

volumes:
  - /root/.cache/huggingface:/root/.cache/huggingface

fleets: [spark]
```

</div>

We use an [instance volume](../../docs/concepts/volumes.md#instance-volumes) to keep model downloads cached across runs. The `lmsysorg/sglang:spark` image is tuned for inference on DGX Spark. Any Arm-compatible image with proper driver support will work if customization is needed.

Run the environment:

<div class="termy">

```shell
$ dstack apply -f .dstack.yml

 BACKEND       GPU     INSTANCE TYPE  PRICE  
 ssh (remtoe)  GB10:1  instance       $0     idle

Submit the run cursor? [y/n]: y
 
 #  NAME    BACKEND       GPU     PRICE  STATUS   SUMBITTED
 1  cursor  ssh (remote)  GB10:1  $0     running  12:24

Launching `cursor`...
---> 100%

To open in VS Code Desktop, use this link:
  vscode://vscode-remote/ssh-remote+cursor/workflow
```

</div>

## What's next?

> Running workloads on DGX Spark with `dstack` works the same way as on any other [backend](../../docs/concepts/backends.md) (including GPU clouds): you can run [dev environments](../../docs/concepts/dev-environments.md) for interactive development, [tasks](../../docs/concepts/tasks.md) for fine tuning, and [services](../../docs/concepts/services.md) for inference through the unified interface.

1. Read the [NVIDIA DGX Spark in-depth review](https://lmsys.org/blog/2025-10-13-nvidia-dgx-spark/) by the SGLang team.
2. Check [dev environments](../../docs/concepts/dev-environments.md), 
    [tasks](../../docs/concepts/tasks.md), [services](../../docs/concepts/services.md), 
    and [fleets](../../docs/concepts/fleets.md)
3. Follow [Quickstart](../../docs/quickstart.md)
4. Join [Discord](https://discord.gg/u8SmfwPpMd)

!!! info "Aknowledgement"
    Thanks to the [Graphsignal](https://graphsignal.com/) team for access to DGX Spark and for supporting testing and validation. Graphsignal provides inference observability tooling used to profile CUDA workloads during both training and inference.
