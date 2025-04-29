# Alignment Handbook

This example shows how use [Alignment Handbook :material-arrow-top-right-thin:{ .external }](https://github.com/huggingface/alignment-handbook){:target="_blank"} with `dstack` to 
fine-tune Gemma 7B on your SFT dataset using one node or multiple nodes. 

??? info "Prerequisites"
    Once `dstack` is [installed](https://dstack.ai/docs/installation), go ahead clone the repo, and run `dstack init`.

    <div class="termy">
 
    ```shell
    $ git clone https://github.com/dstackai/dstack
    $ cd dstack
    $ dstack init
    ```
 
    </div>

## Training configuration recipe

Alignment Handbook's training script reads the model, LoRA, and dataset arguments, as well
as trainer configuration from a YAML file.
This file can be found at [`examples/fine-tuning/alignment-handbook/config.yaml`](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/alignment-handbook/config.yaml).
You can modify it as needed.

> Before you proceed with training, make sure to update the `hub_model_id` in
> [`examples/fine-tuning/alignment-handbook/config.yaml` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/alignment-handbook/config.yaml){:target="_blank"}
> with your HuggingFace username.

## Single-node training

The easiest way to run a training script with `dstack` is by creating a task configuration file.
This file can be found at [`examples/fine-tuning/alignment-handbook/train.dstack.yml` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/alignment-handbook/train.dstack.yml){:target="_blank"}. 
Below is its content: 

```yaml
type: task
name: ah-train

# If `image` is not specified, dstack uses its default image
python: "3.10"
# Ensure nvcc is installed (req. for Flash Attention) 
nvcc: true

# Required environment variables
env:
  - HF_TOKEN
  - ACCELERATE_LOG_LEVEL=info
  - WANDB_API_KEY
# Commands of the task
commands:
  - git clone https://github.com/huggingface/alignment-handbook.git
  - cd alignment-handbook
  - pip install .
  - pip install flash-attn --no-build-isolation
  - pip install wandb
  - accelerate launch
    --config_file recipes/accelerate_configs/multi_gpu.yaml
    --num_processes=$DSTACK_GPUS_NUM
    scripts/run_sft.py
    ../examples/fine-tuning/alignment-handbook/config.yaml
# Uncomment to access TensorBoard
#ports:
#  - 6006
  
resources:
  # Required resources
  gpu: 24GB
```

The task clones Alignment Handbook's repo, installs the dependencies,
and runs the script.

The `DSTACK_GPUS_NUM` environment variable is automatically passed to the container
according to the `resoruce` property.

To run the task, use `dstack apply`:

<div class="termy">

```shell
$ HF_TOKEN=...
$ WANDB_API_KEY=...
$ dstack apply -f examples/fine-tuning/alignment-handbook/train.dstack.yml
```

</div>

If you list `tensorbord` via `report_to` in [`examples/fine-tuning/alignment-handbook/config.yaml`](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/alignment-handbook/config.yaml),
you'll be able to access experiment metrics via `http://localhost:6006` (while the task is running).

## Multi-node training

The multi-node training task configuration file can be found at [`examples/fine-tuning/alignment-handbook/train-distrib.dstack.yml`](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/alignment-handbook/train-distrib.dstack.yml).
Below is its content:

```yaml
type: task
name: ah-train-distrib

# If `image` is not specified, dstack uses its default image
python: "3.10"
# Ensure nvcc is installed (req. for Flash Attention) 
nvcc: true

# The size of cluster
nodes: 2

# Required environment variables
env:
  - HF_TOKEN
  - ACCELERATE_LOG_LEVEL=info
  - WANDB_API_KEY
# Commands of the task (dstack runs it on each node)
commands:
  - git clone https://github.com/huggingface/alignment-handbook.git
  - cd alignment-handbook
  - pip install .
  - pip install flash-attn --no-build-isolation
  - pip install wandb
  - accelerate launch
    --config_file ../examples/fine-tuning/alignment-handbook/fsdp_qlora_full_shard.yaml
    --main_process_ip=$DSTACK_MASTER_NODE_IP
    --main_process_port=8008
    --machine_rank=$DSTACK_NODE_RANK
    --num_processes=$DSTACK_GPUS_NUM
    --num_machines=$DSTACK_NODES_NUM
    scripts/run_sft.py 
    ../examples/fine-tuning/alignment-handbook/config.yaml
# Expose 6006 to access TensorBoard
ports:
  - 6006

resources:
  # Required resources
  gpu: 24GB
  # Shared memory size for inter-process communication
  shm_size: 24GB
```

Here's how the multi-node task is different from the single-node one:

1. The `nodes` property is specified with a number of required nodes (should match the fleet's nodes number).
2. Under `resoruces`, `shm_size` is specified with the shared memory size used for the communication of parallel
   processes within a node (in case multiple GPUs per node are used).
3. Instead of Alignment Handbook's [`recipes/accelerate_configs/multi_gpu.yaml`](https://github.com/huggingface/alignment-handbook/blob/main/recipes/accelerate_configs/multi_gpu.yaml), we use [`examples/fine-tuning/alignment-handbook/fsdp_qlora_full_shard.yaml`](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/alignment-handbook/fsdp_qlora_full_shard.yaml) as an accelerate config.
4. We use `DSTACK_MASTER_NODE_IP`, `DSTACK_NODE_RANK`, `DSTACK_GPUS_NUM`, and `DSTACK_NODES_NUM` environment variables to
   configure `accelerate`. The environment variables are automatically passed
   to the container for each node based on the task configuration.

## Fleets

> By default, `dstack apply` reuses `idle` instances from one of the existing [fleets](https://dstack.ai/docs/fleets). 
If no `idle` instances meet the requirements, it creates a new fleet using one of the configured backends.

The example folder includes two cloud fleet configurations: [`examples/fine-tuning/alignment-handbook/fleet.dstack.yml`](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/alignment-handbook/fleet.dstack.yml) (a single node with a `24GB` GPU),
and a [`examples/fine-tuning/alignment-handbook/fleet-distrib.dstack.yml`](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/alignment-handbook/fleet-distrib.dstack.yml) (a cluster of two nodes each with a `24GB` GPU).

You can update the fleet configurations to change the VRAM size, GPU model, number of GPUs per node, or number of nodes. 

A fleet can be provisioned with `dstack apply`:

<div class="termy">

```shell
$ dstack apply -f examples/fine-tuning/alignment-handbook/fleet.dstack.yml
```

</div>

Once provisioned, the fleet can run dev environments and fine-tuning tasks.
To delete the fleet, use `dstack fleet delete`.

> To ensure `dstack apply` always reuses an existing fleet,
pass `--reuse` to `dstack apply` (or set `creation_policy` to `reuse` in the task configuration).
The default policy is `reuse_or_create`.

## Dev environment

If you'd like to play with the example using a dev environment, run
[`.dstack.yml` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/examples/fine-tuning/alignment-handbook/.dstack.yml){:target="_blank"} via `dstack apply`:

<div class="termy">

```shell
dstack apply -f examples/fine-tuning/alignment-handbook/.dstack.yaml 
```

</div>

## Source code

The source-code of this example can be found in [`examples/fine-tuning/alignment-handbook` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/alignment-handbook){:target="_blank"}.

## What's next?

1. Check [dev environments](https://dstack.ai/docs/dev-environments), [tasks](https://dstack.ai/docs/tasks),
   [services](https://dstack.ai/docs/services), and [fleets](https://dstack.ai/docs/concepts/fleets).
2. Browse [Alignment Handbook :material-arrow-top-right-thin:{ .external }](https://github.com/huggingface/alignment-handbook){:target="_blank"}.
3. See other [examples](/examples).
