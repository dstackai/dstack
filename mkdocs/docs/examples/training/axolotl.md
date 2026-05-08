---
title: Axolotl
description: Fine-tuning Llama models with Axolotl — single-node SFT with FSDP and QLoRA, or distributed across multiple nodes
---

# Axolotl

This example shows how to use [Axolotl](https://github.com/OpenAccess-AI-Collective/axolotl) with `dstack` to fine-tune Llama models — on a single node with SFT, FSDP, and QLoRA, or distributed across multiple nodes.

## Single-node training

This section walks through fine-tuning 4-bit quantized `Llama-4-Scout-17B-16E` using SFT with FSDP and QLoRA.

### Define a configuration

Axolotl reads the model, QLoRA, and dataset arguments, as well as trainer configuration from a [`scout-qlora-flexattn-fsdp2.yaml`](https://github.com/axolotl-ai-cloud/axolotl/blob/main/examples/llama-4/scout-qlora-flexattn-fsdp2.yaml) file. The configuration uses 4-bit axolotl quantized version of `meta-llama/Llama-4-Scout-17B-16E`, requiring only ~43GB VRAM/GPU with 4K context length.

Below is a task configuration that does fine-tuning.

<div editor-title="train.dstack.yml">

```yaml
type: task
# The name is optional, if not specified, generated randomly
name: axolotl-nvidia-llama-scout-train

# Using the official Axolotl's Docker image
image: axolotlai/axolotl:main-latest

# Required environment variables
env:
  - HF_TOKEN
  - WANDB_API_KEY
  - WANDB_PROJECT
  - HUB_MODEL_ID
# Commands of the task
commands:
  - wget https://raw.githubusercontent.com/axolotl-ai-cloud/axolotl/main/examples/llama-4/scout-qlora-flexattn-fsdp2.yaml
  - |
    axolotl train scout-qlora-flexattn-fsdp2.yaml \
      --wandb-project $WANDB_PROJECT \
      --wandb-name $DSTACK_RUN_NAME \
      --hub-model-id $HUB_MODEL_ID

resources:
  # Four GPU (required by FSDP)
  gpu: H100:4
  # Shared memory size for inter-process communication
  shm_size: 64GB
  disk: 500GB..
```

</div>

The task uses Axolotl's Docker image, where Axolotl is already pre-installed.

!!! info "AMD"
    The example above uses NVIDIA accelerators. To use it with AMD, check out [AMD](../accelerators/amd.md#axolotl).

### Run the configuration

Once the configuration is ready, run `dstack apply -f <configuration file>`, and `dstack` will automatically provision the
cloud resources and run the configuration.

<div class="termy">

```shell
$ HF_TOKEN=...
$ WANDB_API_KEY=...
$ WANDB_PROJECT=...
$ HUB_MODEL_ID=...
$ dstack apply -f train.dstack.yml

 #  BACKEND              RESOURCES                     INSTANCE TYPE  PRICE
 1  vastai (cz-czechia)  cpu=64 mem=128GB H100:80GB:2  18794506       $3.8907
 2  vastai (us-texas)    cpu=52 mem=64GB  H100:80GB:2  20442365       $3.6926
 3  vastai (fr-france)   cpu=64 mem=96GB  H100:80GB:2  20379984       $3.7389

Submit the run axolotl-nvidia-llama-scout-train? [y/n]:

Provisioning...
---> 100%
```

</div>

## Distributed training

!!! info "Prerequisites"
    Before running a distributed task, make sure to create a fleet with `placement` set to `cluster` (can be a [managed fleet](../../concepts/fleets.md#cluster-placement) or an [SSH fleet](../../concepts/fleets.md#ssh-placement)).

This section walks through running distributed fine-tuning of `Llama-3.1-70B` with QLoRA and FSDP across multiple nodes.

### Define a configuration

Once the fleet is created, define a distributed task configuration. Here's an example of a distributed `QLoRA` task using `FSDP`.

<div editor-title="train-distrib.dstack.yml">

```yaml
type: task
name: axolotl-multi-node-qlora-llama3-70b

nodes: 2

image: nvcr.io/nvidia/pytorch:25.01-py3

env:
  - HF_TOKEN
  - WANDB_API_KEY
  - WANDB_PROJECT
  - HUB_MODEL_ID
  - CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
  - NCCL_DEBUG=INFO
  - ACCELERATE_LOG_LEVEL=info

commands:
  # Replacing the default Torch and FlashAttention in the NCG container with Axolotl-compatible versions.
  # The preinstalled versions are incompatible with Axolotl.
  - pip uninstall -y torch flash-attn
  - pip install torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/test/cu124
  - pip install --no-build-isolation axolotl[flash-attn,deepspeed]
  - wget https://raw.githubusercontent.com/huggingface/trl/main/examples/accelerate_configs/fsdp1.yaml
  - wget https://raw.githubusercontent.com/axolotl-ai-cloud/axolotl/main/examples/llama-3/qlora-fsdp-70b.yaml
  # Axolotl includes hf-xet version 1.1.0, which fails during downloads. Replacing it with the latest version (1.1.2).
  - pip uninstall -y hf-xet
  - pip install hf-xet --no-cache-dir
  - |
    accelerate launch \
      --config_file=fsdp1.yaml \
      -m axolotl.cli.train qlora-fsdp-70b.yaml \
      --hub-model-id $HUB_MODEL_ID \
      --output-dir /checkpoints/qlora-llama3-70b \
      --wandb-project $WANDB_PROJECT \
      --wandb-name $DSTACK_RUN_NAME \
      --main_process_ip=$DSTACK_MASTER_NODE_IP \
      --main_process_port=8008 \
      --machine_rank=$DSTACK_NODE_RANK \
      --num_processes=$DSTACK_GPUS_NUM \
      --num_machines=$DSTACK_NODES_NUM

resources:
  gpu: 80GB:8
  shm_size: 128GB

volumes:
  - /checkpoints:/checkpoints
```

</div>

!!! info "Docker image"
    We are using `nvcr.io/nvidia/pytorch:25.01-py3` from NGC because it includes the necessary libraries and packages for RDMA and InfiniBand support.

### Run the configuration

To run a configuration, use the [`dstack apply`](../../reference/cli/dstack/apply.md) command.

<div class="termy">

```shell
$ HF_TOKEN=...
$ WANDB_API_KEY=...
$ WANDB_PROJECT=...
$ HUB_MODEL_ID=...
$ dstack apply -f train-distrib.dstack.yml

 #  BACKEND       RESOURCES                       INSTANCE TYPE  PRICE
 1  ssh (remote)  cpu=208 mem=1772GB H100:80GB:8  instance       $0     idle
 2  ssh (remote)  cpu=208 mem=1772GB H100:80GB:8  instance       $0     idle

Submit the run axolotl-multi-node-qlora-llama3-70b? [y/n]: y

Provisioning...
---> 100%
```

</div>

## What's next?

1. Check [dev environments](../../concepts/dev-environments.md), [tasks](../../concepts/tasks.md),
   [services](../../concepts/services.md), and [fleets](../../concepts/fleets.md)
2. Read about [cluster placement](../../concepts/fleets.md#cluster-placement)
3. See the [AMD](../accelerators/amd.md#axolotl) example
