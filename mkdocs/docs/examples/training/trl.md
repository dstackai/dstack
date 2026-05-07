---
title: TRL
description: Fine-tuning Llama with TRL — single-node SFT with QLoRA, or distributed across multiple nodes with FSDP and DeepSpeed
---

# TRL

This example walks you through how to use [TRL](https://github.com/huggingface/trl) with `dstack` to fine-tune `Llama-3.1-8B` — on a single node with SFT and QLoRA, or distributed across multiple nodes with [Accelerate](https://github.com/huggingface/accelerate) and [DeepSpeed](https://github.com/deepspeedai/DeepSpeed).

## Single-node training

### Define a configuration

Below is a task configuration that does fine-tuning.

<div editor-title="train.dstack.yml"> 

```yaml
type: task
name: trl-train

python: 3.12
# Ensure nvcc is installed (req. for Flash Attention) 
nvcc: true

env:
  - HF_TOKEN
  - WANDB_API_KEY
  - HUB_MODEL_ID
commands:
  # Pin torch==2.6.0 to avoid building Flash Attention from source.
  # Prebuilt Flash Attention wheels are not available for the latest torch==2.7.0.
  - uv pip install torch==2.6.0
  - uv pip install transformers bitsandbytes peft wandb
  - uv pip install flash_attn --no-build-isolation
  - git clone https://github.com/huggingface/trl
  - cd trl
  - uv pip install .
  - |
    accelerate launch \
      --config_file=examples/accelerate_configs/multi_gpu.yaml \
      --num_processes $DSTACK_GPUS_PER_NODE \
      trl/scripts/sft.py \
      --model_name meta-llama/Meta-Llama-3.1-8B \
      --dataset_name OpenAssistant/oasst_top1_2023-08-25 \
      --dataset_text_field="text" \
      --per_device_train_batch_size 1 \
      --per_device_eval_batch_size 1 \
      --gradient_accumulation_steps 4 \
      --learning_rate 2e-4 \
      --report_to wandb \
      --bf16 \
      --max_seq_length 1024 \
      --lora_r 16 \
      --lora_alpha 32 \
      --lora_target_modules q_proj k_proj v_proj o_proj \
      --load_in_4bit \
      --use_peft \
      --attn_implementation "flash_attention_2" \
      --logging_steps=10 \
      --output_dir models/llama31 \
      --hub_model_id peterschmidt85/FineLlama-3.1-8B

resources:
  gpu:
    # 24GB or more VRAM
    memory: 24GB..
    # One or more GPU
    count: 1..
  # Shared memory (for multi-gpu)
  shm_size: 24GB
```

</div>

Change the `resources` property to specify more GPUs.

!!! info "AMD"
    The example above uses NVIDIA accelerators. To use it with AMD, check out [AMD](../accelerators/amd.md#trl).

??? info "DeepSpeed"
    For more memory-efficient use of multiple GPUs, consider using DeepSpeed and ZeRO Stage 3.

    To do this, use the `examples/accelerate_configs/deepspeed_zero3.yaml` configuration file instead of 
    `examples/accelerate_configs/multi_gpu.yaml`.

### Run the configuration

Once the configuration is ready, run `dstack apply -f <configuration file>`, and `dstack` will automatically provision the
cloud resources and run the configuration.

<div class="termy">

```shell
$ HF_TOKEN=...
$ WANDB_API_KEY=...
$ HUB_MODEL_ID=...
$ dstack apply -f train.dstack.yml

 #  BACKEND              RESOURCES                     INSTANCE TYPE  PRICE     
 1  vastai (cz-czechia)  cpu=64 mem=128GB H100:80GB:2  18794506       $3.8907   
 2  vastai (us-texas)    cpu=52 mem=64GB  H100:80GB:2  20442365       $3.6926   
 3  vastai (fr-france)   cpu=64 mem=96GB  H100:80GB:2  20379984       $3.7389

Submit the run trl-train? [y/n]:

Provisioning...
---> 100%
```

</div>

## Distributed training

!!! info "Prerequisites"
    Before running a distributed task, make sure to create a fleet with `placement` set to `cluster` (can be a [managed fleet](../../concepts/fleets.md#cluster-placement) or an [SSH fleet](../../concepts/fleets.md#ssh-placement)).

### Define a configuration

Once the fleet is created, define a distributed task configuration. Here's an example using either FSDP or DeepSpeed ZeRO-3.

=== "FSDP"

    <div editor-title="train-distrib.dstack.yml">

    ```yaml
    type: task
    name: trl-train-fsdp-distrib

    nodes: 2

    image: nvcr.io/nvidia/pytorch:25.01-py3

    env:
      - HF_TOKEN
      - ACCELERATE_LOG_LEVEL=info
      - WANDB_API_KEY
      - MODEL_ID=meta-llama/Llama-3.1-8B
      - HUB_MODEL_ID

    commands:
      - pip install transformers bitsandbytes peft wandb
      - git clone https://github.com/huggingface/trl
      - cd trl
      - pip install .
      - |
        accelerate launch \
          --config_file=examples/accelerate_configs/fsdp1.yaml \
          --main_process_ip=$DSTACK_MASTER_NODE_IP \
          --main_process_port=8008 \
          --machine_rank=$DSTACK_NODE_RANK \
          --num_processes=$DSTACK_GPUS_NUM \
          --num_machines=$DSTACK_NODES_NUM \
          trl/scripts/sft.py \
          --model_name $MODEL_ID \
          --dataset_name OpenAssistant/oasst_top1_2023-08-25 \
          --dataset_text_field="text" \
          --per_device_train_batch_size 1 \
          --per_device_eval_batch_size 1 \
          --gradient_accumulation_steps 4 \
          --learning_rate 2e-4 \
          --report_to wandb \
          --bf16 \
          --max_seq_length 1024 \
          --attn_implementation flash_attention_2 \
          --logging_steps=10 \
          --output_dir /checkpoints/llama31-ft \
          --hub_model_id $HUB_MODEL_ID \
          --torch_dtype bfloat16

    resources:
      gpu: 80GB:8
      shm_size: 128GB

    volumes:
      - /checkpoints:/checkpoints
    ```

    </div>

=== "DeepSpeed ZeRO-3"

    <div editor-title="train-distrib.dstack.yml">

    ```yaml
    type: task
    name: trl-train-deepspeed-distrib

    nodes: 2

    image: nvcr.io/nvidia/pytorch:25.01-py3

    env:
      - HF_TOKEN
      - WANDB_API_KEY
      - HUB_MODEL_ID
      - MODEL_ID=meta-llama/Llama-3.1-8B
      - ACCELERATE_LOG_LEVEL=info

    commands:
      - pip install transformers bitsandbytes peft wandb deepspeed
      - git clone https://github.com/huggingface/trl
      - cd trl
      - pip install .
      - |
        accelerate launch \
          --config_file=examples/accelerate_configs/deepspeed_zero3.yaml \
          --main_process_ip=$DSTACK_MASTER_NODE_IP \
          --main_process_port=8008 \
          --machine_rank=$DSTACK_NODE_RANK \
          --num_processes=$DSTACK_GPUS_NUM \
          --num_machines=$DSTACK_NODES_NUM \
          trl/scripts/sft.py \
          --model_name $MODEL_ID \
          --dataset_name OpenAssistant/oasst_top1_2023-08-25 \
          --dataset_text_field="text" \
          --per_device_train_batch_size 1 \
          --per_device_eval_batch_size 1 \
          --gradient_accumulation_steps 4 \
          --learning_rate 2e-4 \
          --report_to wandb \
          --bf16 \
          --max_seq_length 1024 \
          --attn_implementation flash_attention_2 \
          --logging_steps=10 \
          --output_dir /checkpoints/llama31-ft \
          --hub_model_id $HUB_MODEL_ID \
          --torch_dtype bfloat16

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
$ HUB_MODEL_ID=...
$ dstack apply -f train-distrib.dstack.yml

 #  BACKEND       RESOURCES                       INSTANCE TYPE  PRICE
 1  ssh (remote)  cpu=208 mem=1772GB H100:80GB:8  instance       $0     idle
 2  ssh (remote)  cpu=208 mem=1772GB H100:80GB:8  instance       $0     idle

Submit the run trl-train-fsdp-distrib? [y/n]: y

Provisioning...
---> 100%
```

</div>

## What's next?

1. Check [dev environments](../../concepts/dev-environments.md), [tasks](../../concepts/tasks.md), 
   [services](../../concepts/services.md), and [fleets](../../concepts/fleets.md)
2. Read about [cluster placement](../../concepts/fleets.md#cluster-placement)
3. See the [AMD](../accelerators/amd.md#trl) example
