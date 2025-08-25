# Open-R1

This example demonstrates how to use `dstack` and [open-r1](https://github.com/huggingface/open-r1) to run GRPO training across distributed nodes, dedicating one node for [vLLM](https://github.com/vllm-project/vllm) inference while using the remaining nodes for training. 

??? info "Prerequisites"
    Once `dstack` is [installed](https://dstack.ai/docs/installation), go ahead clone the repo, and run `dstack init`.

    <div class="termy">
 
    ```shell
    $ git clone https://github.com/dstackai/dstack
    $ cd dstack
    $ dstack init
    ```
    </div>

## Create fleet

Before submitting distributed training runs, make sure to create a fleet with a `placement` set to `cluster`.

> For more detials on how to use clusters with `dstack`, check the [Clusters](https://dstack.ai/docs/guides/clusters) guide.

## Define a configurtation

Once the fleet is created, define a distributed task configuration.

<div editor-title="examples/distributed-training/open-r1/.dstack.yml">

```yaml
type: task
name: open-r1-grpo

# Size of the cluster
nodes: 2

python: 3.12

nvcc: true

# Required environment variables
env:
  - HF_TOKEN
  - HUB_MODEL_ID
  - WANDB_API_KEY
  - NCCL_DEBUG=INFO
  # VLLM configuration
  - USE_VLLM=true
  - MODEL=Qwen/Qwen2.5-Coder-7B-Instruct
  - TP=4
  - DP=2

# Commands of the task
commands:
  - uv pip install vllm==0.8.5.post1
  - uv pip install setuptools
  - uv pip install https://github.com/Dao-AILab/flash-attention/releases/download/v2.7.4.post1/flash_attn-2.7.4.post1+cu12torch2.6cxx11abiFALSE-cp312-cp312-linux_x86_64.whl 
  - git clone https://github.com/huggingface/open-r1.git
  - cd open-r1
  - uv pip install .
  - |
    # Get the last IP from DSTACK_NODES_IPS for vLLM node
    VLLM_HOST=$(echo $DSTACK_NODES_IPS | tr ' ' '\n' | tail -n 1)
    echo "VLLM host IP (last node): $VLLM_HOST"
    
    if [ "$USE_VLLM" = "true" ]; then
      if [ "$DSTACK_NODE_RANK" -eq $(($DSTACK_NODES_NUM - 1)) ]; then
        # Last Node runs VLLM server
        echo "Starting VLLM server on Last Node (IP: $VLLM_HOST)"
        trl vllm-serve --model $MODEL  --tensor_parallel_size $TP --data_parallel_size $DP --host 0.0.0.0
      else
        # Training node - adjust world size and nodes count for training
        GPUS_PER_NODE=$(($DSTACK_GPUS_NUM / $DSTACK_NODES_NUM))
        ADJUSTED_NODES_NUM=$(($DSTACK_NODES_NUM - 1))
        ADJUSTED_GPUS_TOTAL=$(($GPUS_PER_NODE * $ADJUSTED_NODES_NUM))
        # Other nodes run training
        echo "Starting training with VLLM on $VLLM_HOST"
        accelerate launch --config_file recipes/accelerate_configs/zero3.yaml \
            --num_processes=$ADJUSTED_GPUS_TOTAL \
            --num_machines=$ADJUSTED_NODES_NUM \
            --machine_rank=$DSTACK_NODE_RANK \
            --main_process_ip=$DSTACK_MASTER_NODE_IP \
            --main_process_port=8008 \
            src/open_r1/grpo.py \
            --config recipes/Qwen2.5-1.5B-Instruct/grpo/config_demo.yaml \
            --model_name_or_path $MODEL \
            --output_dir /checkpoints/Qwen2.5-Coder-7B-Instruct-GRPO \
            --hub_model_id $HUB_MODEL_ID \
            --vllm_server_host=$VLLM_HOST
      fi
    else
      # Standard training mode without VLLM
      echo "Running standard training without VLLM"
      accelerate launch --config_file recipes/accelerate_configs/zero3.yaml \
            --num_processes=$DSTACK_GPUS_NUM \
            --num_machines=$DSTACK_NODES_NUM \
            --machine_rank=$DSTACK_NODE_RANK \
            --main_process_ip=$DSTACK_MASTER_NODE_IP \
            --main_process_port=8008 \
            src/open_r1/grpo.py \
            --config recipes/Qwen2.5-1.5B-Instruct/grpo/config_demo.yaml \
            --model_name_or_path $MODEL \
            --output_dir /checkpoints/Qwen2.5-Coder-7B-Instruct-GRPO \
            --hub_model_id $HUB_MODEL_ID \
            --use_vllm false
    fi

resources:
  gpu: 80GB:8
  shm_size: 128GB

volumes:
   - /checkpoints:/checkpoints
```
</div>

!!! info "NOTE:"
    1. When `nodes: N` and `USE_VLLM=true`, (N-1) nodes will be used for distributed training, while last node will be used for vLLM inference.
    2. When `USE_VLLM=false`, training happens across all nodes. 
    3. The number of `attention heads` of the model should be divisible by `TP` and `DP` values.
    4. We pin the `flash-attn` to `2.7.4.post1` for compatibility with `vllm=0.8.5.post1`, as latest vLLM causes TRL's GRPO to fail. See [issue #3608](https://github.com/huggingface/trl/issues/3608) for details. 


### Apply the configuration

To run a configuration, use the [`dstack apply`](https://dstack.ai/docs/reference/cli/dstack/apply.md) command.

<div class="termy">

```shell
$ HF_TOKEN=...
$ HUB_MODEL_ID=...
$ WANDB_API_KEY=...
$ dstack apply -f examples/distributed-training/open-r1/.dstack.yml

 #  BACKEND       RESOURCES                       INSTANCE TYPE  PRICE       
 1  ssh (remote)  cpu=208 mem=1772GB H100:80GB:8  instance       $0     idle 
 2  ssh (remote)  cpu=208 mem=1772GB H100:80GB:8  instance       $0     idle  
    
Submit the run open-r1-grpo? [y/n]: y

Provisioning...
---> 100%
```
</div>

## Source code

The source-code of this example can be found in 
[`examples/distributed-training/open-r1` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/distributed-training/open-r1){:target="_blank"}.

!!! info "What's next?"
    1. Read the [clusters](https://dstack.ai/docs/guides/clusters) guide
    2. Check [dev environments](https://dstack.ai/docs/concepts/dev-environments), [tasks](https://dstack.ai/docs/concepts/tasks), 
       [services](https://dstack.ai/docs/concepts/services), and [fleets](https://dstack.ai/docs/concepts/fleets)
    
