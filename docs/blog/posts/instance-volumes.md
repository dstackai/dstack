---
title: "Introducing instance volumes to persist data on instances"
date: 2024-11-05
description: "To simplify caching across runs and the use of NFS, we introduce a new volume type that persists data on the instance."
image: https://dstack.ai/static-assets/static-assets/images/dstack-instance-volumes.png
slug: instance-volumes
categories:
  - Volumes 
---

# Introducing instance volumes to persist data on instances

## How it works { style="display:none" }

Until now, `dstack` supported data persistence only with network volumes, managed by clouds.
While convenient, sometimes you might want to use a simple cache on the instance or 
mount an NFS share to your SSH fleet. To address this, we're now introducing instance volumes that work for both cases.

<div editor-title="examples/misc/volumes/cache.dstack.yml"> 
    
```yaml 
type: task 
name: llama32-task

env:
  - HF_TOKEN
  - MODEL_ID=meta-llama/Llama-3.2-3B-Instruct
commands:
  - pip install vllm
  - vllm serve $MODEL_ID --max-model-len 4096
ports: [8000]

volumes:
  - /root/.dstack/cache:/root/.cache

resources:
  gpu: 16GB..
```

</div>

<!-- more -->

> Instance volumes work with both [SSH fleets](../../docs/concepts/fleets.md#ssh)
> and [cloud fleets](../../docs/concepts/fleets.md#cloud), and it is possible to mount any folders on the instance,
> whether they are regular folders or NFS share mounts.

The configuration above mounts `/root/.dstack/cache` on the instance to `/root/.cache` inside container.

## Caching data on fleet instances { #caching }

If you use a folder on the instance that is not an NFS mount, instance volumes can only be used for caching purposes, as
their state is bound to a particular instance while it's up.

Caching can be especially useful if you want to re-run the same configuration on the same fleet and avoid downloading
very large models, datasets, or dependencies with each run.

## Using NFS with SSH and cloud fleets { #nfs }

If you want to replicate the state across instances, you can mount an NFS share to the instance folder.

With SSH fleets, it's easy to set up an NFS share, as you can do it when logging into your hosts via SSH.
If you'd like to mount NFS with your cloud fleets, you will need to use a custom AMI for that.

Here's an example of a dev environment that mounts the `data` folder from an NFS share, which is mounted to
`/mnt/nfs-storage` on the instance, to the `/data` folder inside the container.

<div editor-title="examples/misc/volumes/nfs.dstack.yml"> 
    
```yaml 
type: dev-environment
name: vscode-nfs

ide: vscode

volumes:
  - /mnt/nfs-storage/data:/data
```

</div>

## Feedback

If you find something not working as intended, please be sure to report it to
[GitHub issues :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/issues){:target="_ blank"}. 
Your feedback and feature requests is also very welcome on our 
[Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"} server.
