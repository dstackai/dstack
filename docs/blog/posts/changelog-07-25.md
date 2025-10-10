---
title: "Rolling deployment, Secrets, Files, Tenstorrent, and more"
date: 2025-07-10
description: "TBA"
slug: changelog-07-25
image: https://dstack.ai/static-assets/static-assets/images/changelog-07-25.png
categories:
  - Changelog
---

# Rolling deployment, Secrets, Files, Tenstorrent, and more

Thanks to feedback from the community, `dstack` continues to evolve. Here’s a look at what’s new.

#### Rolling deployments

Previously, updating running services could cause downtime. The latest release fixes this with [rolling deployments](../../docs/concepts/services.md/#rolling-deployment). Replicas are now updated one by one, allowing uninterrupted traffic during redeployments.

<div class="termy">

```shell
$ dstack apply -f .dstack.yml

Active run my-service already exists. Detected changes that can be updated in-place:
- Repo state (branch, commit, or other)
- File archives
- Configuration properties:
  - env
  - files

Update the run? [y/n]: y 
⠋ Launching my-service...

 NAME                      BACKEND          PRICE    STATUS       SUBMITTED
 my-service deployment=1                             running      11 mins ago
   replica=0 deployment=0  aws (us-west-2)  $0.0026  terminating  11 mins ago
   replica=1 deployment=1  aws (us-west-2)  $0.0026  running      1 min ago
```

</div>

<!-- more -->

#### Secrets

Secrets let you centrally manage sensitive data like API keys and credentials. They’re scoped to a project, managed by project admins, and can be [securely referenced](../../docs/concepts/secrets.md) in run configurations.

<div editor-title=".dstack.yml"> 

```yaml hl_lines="7" 
type: task
name: train

image: nvcr.io/nvidia/pytorch:25.05-py3
registry_auth:
  username: $oauthtoken
  password: ${{ secrets.ngc_api_key }}

commands:
  - git clone https://github.com/pytorch/examples.git pytorch-examples
  - cd pytorch-examples/distributed/ddp-tutorial-series
  - pip install -r requirements.txt
  - |
    torchrun \
      --nproc-per-node=$DSTACK_GPUS_PER_NODE \
      --nnodes=$DSTACK_NODES_NUM \
      multinode.py 50 10

resources:
  gpu: H100:1..2
  shm_size: 24GB
```

</div>

#### Files

By default, `dstack` mounts the repo directory (where you ran `dstack init`) to all runs.

If the directory is large or you need files outside of it, use the new [files](../../docs/concepts/dev-environments/#files) property to map specific local paths into the container.

<div editor-title=".dstack.yml"> 

```yaml
type: task
name: trl-sft

files:
  - .:examples  # Maps the directory where `.dstack.yml` to `/workflow/examples`
  - ~/.ssh/id_rsa:/root/.ssh/id_rsa  # Maps `~/.ssh/id_rsa` to `/root/.ssh/id_rs

python: 3.12

env:
  - HF_TOKEN
  - HF_HUB_ENABLE_HF_TRANSFER=1
  - MODEL=Qwen/Qwen2.5-0.5B
  - DATASET=stanfordnlp/imdb

commands:
  - uv pip install trl
  - | 
    trl sft \
      --model_name_or_path $MODEL --dataset_name $DATASET
      --num_processes $DSTACK_GPUS_PER_NODE

resources:
  gpu: H100:1
```

</div>

#### Tenstorrent

`dstack` remains committed to supporting multiple GPU vendors—including NVIDIA, AMD, TPUs, and more recently, [Tenstorrent :material-arrow-top-right-thin:{ .external }](https://tenstorrent.com/){:target="_blank"}. The latest release improves Tenstorrent support by handling hosts with multiple N300 cards and adds Docker-in-Docker support.

<img src="https://dstack.ai/static-assets/static-assets/images/dstack-tenstorrent-n300.png" width="630"/>

Huge thanks to the Tenstorrent community for testing these improvements!

#### Docker in Docker 

Using Docker inside `dstack` run configurations is now even simpler. Just set `docker` to `true` to [enable the use of Docker CLI](../../docs/concepts/tasks.md#docker-in-docker) in your runs—allowing you to build images, run containers, use Docker Compose, and more.

<div editor-title=".dstack.yml"> 

```yaml
type: task
name: docker-nvidia-smi

docker: true

commands:
  - |
    docker run --gpus all \
      nvidia/cuda:12.3.0-base-ubuntu22.04 \
      nvidia-smi

resources:
  gpu: H100:1
```

</div>

#### AWS EFA

EFA is a network interface for EC2 that enables low-latency, high-bandwidth communication between nodes—crucial for scaling distributed deep learning. With `dstack`, EFA is automatically enabled when using supported instance types in fleets. Check out our [example](../../examples/clusters/efa/index.md)

#### Default Docker images

If no `image` is specified, `dstack` uses a base Docker image that now comes pre-configured with `uv`, `python`, `pip`, essential CUDA drivers, InfiniBand, and NCCL tests (located at `/opt/nccl-tests/build`).  

<div editor-title="examples/clusters/nccl-tests/.dstack.yml">

```yaml
type: task
name: nccl-tests

nodes: 2

startup_order: workers-first
stop_criteria: master-done

env:
  - NCCL_DEBUG=INFO
commands:
  - |
    if [ $DSTACK_NODE_RANK -eq 0 ]; then
      mpirun \
        --allow-run-as-root \
        --hostfile $DSTACK_MPI_HOSTFILE \
        -n $DSTACK_GPUS_NUM \
        -N $DSTACK_GPUS_PER_NODE \
        --bind-to none \
        /opt/nccl-tests/build/all_reduce_perf -b 8 -e 8G -f 2 -g 1
    else
      sleep infinity
    fi

resources:
  gpu: nvidia:1..8
  shm_size: 16GB
```

</div>

These images are optimized for common use cases and kept lightweight—ideal for everyday development, training, and inference.

#### Server performance

Server-side performance has been improved. With optimized handling and background processing, each server replica can now handle more runs.

#### Google SSO

Alongside the open-source version, `dstack` also offers [dstack Enterprise :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack-enterprise){:target="_blank"} — which adds dedicated support and extra integrations like Single Sign-On (SSO). The latest release introduces support for configuring your company’s Google account for authentication.

<img src="https://dstack.ai/static-assets/static-assets/images/dstack-enterprise-google-sso.png" width="630"/>

If you’d like to learn more about `dstack` Enterprise, [let us know](https://calendly.com/dstackai/discovery-call).

That’s all for now. 

!!! info "What's next?"
    Give dstack a try, and share your feedback—whether it’s [GitHub :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack){:target="_blank"} issues, PRs, or questions on [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"}. We’re eager to hear from you!
