# TRL

This example walks you through how to use [TRL :material-arrow-top-right-thin:{ .external }](https://github.com/huggingface/trl){:target="_blank"} to fine-tune `Llama-3.1-8B` with `dstack` using SFT with QLoRA.

## Define a configuration

Below is a task configuration that does fine-tuning.

<div editor-title="examples/single-node-training/trl/train.dstack.yml"> 

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
    The example above uses NVIDIA accelerators. To use it with AMD, check out [AMD](https://dstack.ai/examples/accelerators/amd#trl).

??? info "DeepSpeed"
    For more memory-efficient use of multiple GPUs, consider using DeepSpeed and ZeRO Stage 3.

    To do this, use the `examples/accelerate_configs/deepspeed_zero3.yaml` configuration file instead of 
    `examples/accelerate_configs/multi_gpu.yaml`.

## Run the configuration

Once the configuration is ready, run `dstack apply -f <configuration file>`, and `dstack` will automatically provision the
cloud resources and run the configuration.

<div class="termy">

```shell
$ HF_TOKEN=...
$ WANDB_API_KEY=...
$ HUB_MODEL_ID=...
$ dstack apply -f examples/single-node-training/trl/train.dstack.yml

 #  BACKEND              RESOURCES                     INSTANCE TYPE  PRICE     
 1  vastai (cz-czechia)  cpu=64 mem=128GB H100:80GB:2  18794506       $3.8907   
 2  vastai (us-texas)    cpu=52 mem=64GB  H100:80GB:2  20442365       $3.6926   
 3  vastai (fr-france)   cpu=64 mem=96GB  H100:80GB:2  20379984       $3.7389

Submit the run trl-train? [y/n]:

Provisioning...
---> 100%
```

</div>

## Source code

The source-code of this example can be found in 
[`examples/llms/llama31` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/llms/llama31){:target="_blank"} and [`examples/single-node-training/trl` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/single-node-training/trl){:target="_blank"}.

## What's next?

1. Browse the [TRL distributed training](https://dstack.ai/docs/examples/distributed-training/trl) example
2. Check [dev environments](https://dstack.ai/docs/dev-environments), [tasks](https://dstack.ai/docs/tasks), 
   [services](https://dstack.ai/docs/services), and [fleets](https://dstack.ai/docs/fleets)
3. See the [AMD](https://dstack.ai/examples/accelerators/amd#trl) example 
