# TRL

This example walks you through how to run distributed fine-tune using [TRL](https://github.com/huggingface/trl), [Accelerate](https://github.com/huggingface/accelerate) and [Deepspeed](https://github.com/deepspeedai/DeepSpeed).

!!! info "Prerequisites"
    Before running a distributed task, make sure to create a fleet with `placement` set to `cluster` (can be a [managed fleet](https://dstack.ai/docs/concepts/fleets#backend-placement) or an [SSH fleet](https://dstack.ai/docs/concepts/fleets#ssh-placement)).

## Define a configuration

Once the fleet is created, define a distributed task configuration. Here's an example of such a task.

=== "FSDP"

    <div editor-title="examples/distributed-training/trl/fsdp.dstack.yml">
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

=== "Deepseed ZeRO-3"

    <div editor-title="examples/distributed-training/trl/deepspeed.dstack.yml">
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

### Apply the configuration

To run a configuration, use the [`dstack apply`](https://dstack.ai/docs/reference/cli/dstack/apply.md) command.

<div class="termy">

```shell
$ HF_TOKEN=...
$ WANDB_API_KEY=...
$ HUB_MODEL_ID=...
$ dstack apply -f examples/distributed-training/trl/fsdp.dstack.yml

 #  BACKEND       RESOURCES                       INSTANCE TYPE  PRICE
 1  ssh (remote)  cpu=208 mem=1772GB H100:80GB:8  instance       $0     idle
 2  ssh (remote)  cpu=208 mem=1772GB H100:80GB:8  instance       $0     idle

Submit the run trl-train-fsdp-distrib? [y/n]: y

Provisioning...
---> 100%
```
</div>

## Source code

The source-code of this example can be found in
[`examples/distributed-training/trl`](https://github.com/dstackai/dstack/blob/master/examples/distributed-training/trl).

!!! info "What's next?"
    1. Read the [clusters](https://dstack.ai/docs/guides/clusters) guide
    2. Check [dev environments](https://dstack.ai/docs/concepts/dev-environments), [tasks](https://dstack.ai/docs/concepts/tasks),
       [services](https://dstack.ai/docs/concepts/services), and [fleets](https://dstack.ai/docs/concepts/fleets)
