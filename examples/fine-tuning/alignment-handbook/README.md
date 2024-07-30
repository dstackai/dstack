# Alignment Handbook

[Alignment Handbook](https://github.com/huggingface/alignment-handbook) by HuggingFace offers recipes, configs, and
scripts for fine-tuning LLMs. It includes all the code needed to run CPT, SFT, DPO, and ORPO leveraging HuggingFace's
libraries like `transformers`, `peft`, `accelerate`, and `trl`. You just need to modify the recipes and run the 
appropriate script.

This example shows how use Alignment Handbook to fine-tune Gemma 7B on your SFT dataset 
with Alignment Handbook and `dstack`. 

## Prerequisites

Before following this tutorial, ensure you've [installed](https://dstack.ai/docs/installation) `dstack`.

### Fleets

The example folder includes two cloud fleet configurations: [fleet.dstack.yml](fleet.dstack.yml) (a single node with a `24GB` GPU),
and a [fleet-distrib.dstack.yml](fleet-distrib.dstack.yml) (a cluster of two nodes eah with a `24GB` GPU).

You can update the fleet configurations to change the vRAM size, GPU model, number of GPUs per node, or number of nodes. 

A fleet can be provisioned with `dstack apply`:

```shell
dstack apply -f examples/fine-tuning/alignment-handbook/fleet.dstack.yml
```

Once provisioned, the fleet can run dev environments and fine-tuning tasks.
To delete the fleet, use `dstack fleet delete`.

### Training configuration recipe

Alignment Handbook's training script reads the training configuration recipe  
from a YAML file. It includes the model, LoRA, and dataset arguments, as well
as trainer configuration.

This file can be found at [config.yaml](config.yaml).
You can modify it as needed.

## Single-node training

The easiest way to run a training script with `dstack` is by creating a task configuration file.
This file can be found at [train.dstack.yml](train.dstack.yml). Below is its content: 

```yaml
type: task
name: ah-train

# If `image` is not specified, dstack uses its default image
python: "3.10"

# Required environment variables
env:
  - HUGGING_FACE_HUB_TOKEN
  - ACCELERATE_LOG_LEVEL=info
  - WANDB_API_KEY
# Commands of the task
commands:
  - conda install cuda
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
# Expose 6006 to access TensorBoard
ports:
  - 6006
  
resources:
  # Required resources
  gpu: 24GB
```

The task clones Alignment Handbook's repo, installs the dependencies,
and runs the script.

The `DSTACK_GPUS_NUM` environment variable is automatically passed to the container
according to the `resoruce` property.

To run the task, use `dstack apply`:

```shell
HUGGING_FACE_HUB_TOKEN=...
ACCELERATE_LOG_LEVEL=...
WANDB_API_KEY=...

dstack apply -f examples/fine-tuning/alignment-handbook/train.dstack.yml
```

To ensure the task never creates a new fleet,
pass `--reuse` to `dstack apply` (or set `creation_policy` to `reuse` in the task configuration).
The default policy is `reuse_or_create`.

If you list `tensorbord` via `report_to` in [config.yaml](config.yaml),
you'll be able to access experiment metrics via `http://localhost:6006` (while the task is running).

## Multi-node training

The multi-node training task configuration file can be found at [train-distrib.dstack.yml](train-distrib.dstack.yml).
Below is its content:

```
type: task
name: ah-train-distrib

# If `image` is not specified, dstack uses its default image
python: "3.10"

# Required environment variables
env:
  - HUGGING_FACE_HUB_TOKEN
  - ACCELERATE_LOG_LEVEL=info
  - WANDB_API_KEY
# Commands of the task (dstack runs it on each node)
commands:
  - conda install cuda
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

# The number of interconnected instances required
nodes: 2

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
3. Instead of `recipes/accelerate_configs/multi_gpu.yaml`, we use [fsdp_qlora_full_shard.yaml](fsdp_qlora_full_shard.yaml) as an accelerate config.
4. We use `DSTACK_MASTER_NODE_IP`, `DSTACK_NODE_RANK`, `DSTACK_GPUS_NUM`, and `DSTACK_NODES_NUM` environment variables to
   configure `accelerate`. The environment variables are automatically passed
   to the container for each node based on the task configuration.

## Dev environment

If you'd like to play with the example using a dev environment, run
[.dstack.yml](.dstack.yml) via `dstack apply`:

```shell
dstack apply -f examples/fine-tuning/alignment-handbook/.dstack.yaml 
```

## What's next?

1. Browse [Alignment Handbook](https://github.com/huggingface/alignment-handbook).
2. Check [dev environments](https://dstack.ai/docs/dev-environments), [tasks](https://dstack.ai/docs/tasks), 
   [services](https://dstack.ai/docs/services), and [fleets](https://dstack.ai/docs/fleets).
3. See other [examples](../..).