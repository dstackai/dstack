# TRL

This example walks you through how to fine-tune [Llama-3.1-8B :material-arrow-top-right-thin:{ .external }](https://huggingface.co/meta-llama/Llama-3.1-8B){:target="_blank"} with `dstack`, whether in the cloud or
on-prem.

## Single-node Training

Below is an example for `QLORA fine-tuning` Llama 3.1 8B using
the [`OpenAssistant/oasst_top1_2023-08-25` :material-arrow-top-right-thin:{ .external }](https://huggingface.co/datasets/OpenAssistant/oasst_top1_2023-08-25){:target="_blank"}
dataset:

<div editor-title="examples/single-node-training/trl/train.dstack.yml"> 

```yaml
type: task
name: trl-train

python: "3.10"
# Ensure nvcc is installed (req. for Flash Attention) 
nvcc: true

env:
  - HF_TOKEN
  - WANDB_API_KEY
commands:
  - pip install "transformers>=4.43.2"
  - pip install bitsandbytes
  - pip install flash-attn --no-build-isolation
  - pip install peft
  - pip install wandb
  - git clone https://github.com/huggingface/trl
  - cd trl
  - pip install .
  - accelerate launch
    --config_file=examples/accelerate_configs/multi_gpu.yaml
    --num_processes $DSTACK_GPUS_PER_NODE 
    examples/scripts/sft.py
    --model_name meta-llama/Meta-Llama-3.1-8B
    --dataset_name OpenAssistant/oasst_top1_2023-08-25
    --dataset_text_field="text"
    --per_device_train_batch_size 1
    --per_device_eval_batch_size 1
    --gradient_accumulation_steps 4
    --learning_rate 2e-4
    --report_to wandb
    --bf16
    --max_seq_length 1024
    --lora_r 16 --lora_alpha 32
    --lora_target_modules q_proj k_proj v_proj o_proj
    --load_in_4bit
    --use_peft
    --attn_implementation "flash_attention_2"
    --logging_steps=10
    --output_dir models/llama31
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
    The example above uses NVIDIA accelerators. To use it with AMD, check out [AMD](https://dstack.ai/examples/accelerators/amd#trl).

### DeepSpeed

For more memory-efficient use of multiple GPUs, consider using DeepSpeed and ZeRO Stage 3.

To do this, use the `examples/accelerate_configs/deepspeed_zero3.yaml` configuration file instead of 
`examples/accelerate_configs/multi_gpu.yaml`.

[//]: # (TODO: Find a better example for a multi-node training)

## Fleets

By default, `dstack apply` reuses `idle` instances from one of the existing [fleets](https://dstack.ai/docs/fleets).
If no `idle` instances meet the requirements, it creates a new fleet using one of the configured backends.

Use [fleets](https://dstack.ai/docs/fleets.md) configurations to create fleets manually. This reduces startup time for dev environments,
tasks, and services, and is very convenient if you want to reuse fleets across runs.

## Dev environments

Before running a task or service, it's recommended that you first start with
a [dev environment](https://dstack.ai/docs/dev-environments). Dev environments
allow you to run commands interactively.

## Source code

The source-code of this example can be found in 
[`examples/llms/llama31` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/llms/llama31){:target="_blank"} and [`examples/single-node-training/trl` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/single-node-training/trl){:target="_blank"}.

## What's next?

1. Browse the [TRL Distributed Training](https://dstack.ai/docs/examples/distributed-training/trl) and [Axolotl](https://dstack.ai/docs/examples/single-node-training/axolotl) examples.
2. See [AMD](https://dstack.ai/examples/accelerators/amd#axolotl). 
3. Check [dev environments](https://dstack.ai/docs/dev-environments), [tasks](https://dstack.ai/docs/tasks), 
   [services](https://dstack.ai/docs/services),[clusters](https://dstack.ai/docs/guides/clusters) and [fleets](https://dstack.ai/docs/fleets).
