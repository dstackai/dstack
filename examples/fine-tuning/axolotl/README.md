# Axolotl

This example shows how use [Axolotl :material-arrow-top-right-thin:{ .external }](https://github.com/OpenAccess-AI-Collective/axolotl){:target="_blank"} 
with `dstack` to fine-tune 4-bit Quantized [Llama-4-Scout-17B-16E :material-arrow-top-right-thin:{ .external }](https://huggingface.co/axolotl-quants/Llama-4-Scout-17B-16E-Linearized-bnb-nf4-bf16){:target="_blank"} in `single-node` setup and fine-tune [Llama-3-70b-fp16 :material-arrow-top-right-thin:{ .external}](https://huggingface.co/casperhansen/llama-3-70b-fp16) in `multi-node` setup using FSDP and QLoRA.

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

Axolotl reads the model, QLoRA, and dataset arguments, as well as trainer configuration from a [`scout-qlora-fsdp1.yaml` :material-arrow-top-right-thin:{ .external }](https://github.com/axolotl-ai-cloud/axolotl/blob/main/examples/llama-4/scout-qlora-fsdp1.yaml){:target="_blank"} file. The configuration uses 4-bit axolotl quantized version of `meta-llama/Llama-4-Scout-17B-16E`, requiring only ~43GB VRAM/GPU with 4K context length.


## Single-node training

The easiest way to run a training script with `dstack` is by creating a task configuration file.
This file can be found at [`examples/fine-tuning/axolotl/.dstack.yml` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/axolotl/.dstack.yaml){:target="_blank"}.

<div editor-title="examples/fine-tuning/axolotl/.dstack.yml">

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
  - WANDB_NAME=axolotl-nvidia-llama-scout-train
  - HUB_MODEL_ID
# Commands of the task
commands:
  - wget https://raw.githubusercontent.com/axolotl-ai-cloud/axolotl/main/examples/llama-4/scout-qlora-fsdp1.yaml
  - axolotl train scout-qlora-fsdp1.yaml 
            --wandb-project $WANDB_PROJECT 
            --wandb-name $WANDB_NAME 
            --hub-model-id $HUB_MODEL_ID

resources:
  # Two GPU (required by FSDP)
  gpu: H100:2
  # Shared memory size for inter-process communication
  shm_size: 24GB
  disk: 500GB..
```

</div>

The task uses Axolotl's Docker image, where Axolotl is already pre-installed.

!!! info "AMD"
    The example above uses NVIDIA accelerators. To use it with AMD, check out [AMD](https://dstack.ai/examples/accelerators/amd#axolotl).

## Multi-node training

In case the model doesn't feet into a single GPU, consider running a `dstack` task on multiple nodes. Here's an example of distributed `QLORA` task using `FSDP`. Before submitting distributed training runs, make sure to create a fleet with a `placement` set to `cluster`.

> For more detials on how to use clusters with `dstack`, check the [Clusters](https://dstack.ai/docs/guides/clusters) guide.

<div editor-title="examples/distributed-training/axolotl/.dstack.yml">

```yaml
type: task
# The name is optional, if not specified, generated randomly
name: axolotl-multi-node-qlora-llama3-70b

# Size of the cluster
nodes: 2

# The axolotlai/axolotl:main-latest image does not include InfiniBand or RDMA libraries, so we need to use the NGC container.
image: nvcr.io/nvidia/pytorch:25.01-py3
# Required environment variables
env:
  - HF_TOKEN
  - ACCELERATE_LOG_LEVEL=info
  - WANDB_API_KEY
  - NCCL_DEBUG=INFO
  - CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
  - WANDB_NAME=axolotl-dist-llama-qlora-train
  - WANDB_PROJECT
  - HUB_MODEL_ID
# Commands of the task
commands:
  # Replacing the default Torch and FlashAttention in the NCG container with Axolotl-compatible versions.
  # The preinstalled versions are incompatible with Axolotl.
  - uv pip uninstall -y torch flash-attn
  - uv pip install torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/test/cu124
  - uv pip install --no-build-isolation axolotl[flash-attn,deepspeed]
  - wget https://raw.githubusercontent.com/huggingface/trl/main/examples/accelerate_configs/fsdp1.yaml
  - wget https://raw.githubusercontent.com/axolotl-ai-cloud/axolotl/main/examples/llama-3/qlora-fsdp-70b.yaml
  # Axolotl includes hf-xet version 1.1.0, which fails during downloads. Replacing it with the latest version (1.1.2).
  - uv pip uninstall -y hf-xet
  - uv pip install hf-xet --no-cache-dir
  - |
    accelerate launch \
      --config_file=fsdp1.yaml \
      -m axolotl.cli.train qlora-fsdp-70b.yaml \
      --hub-model-id $HUB_MODEL_ID \
      --output-dir /checkpoints/qlora-llama3-70b \
      --wandb-project $WANDB_PROJECT \
      --wandb-name $WANDB_NAME \
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

!!! Note
    We are using the NGC container because it includes the necessary libraries and packages for RDMA and InfiniBand support.

## Running a configuration

Once the configuration is ready, run `dstack apply -f <configuration file>`, and `dstack` will automatically provision the
cloud resources and run the configuration.

<div class="termy">

```shell
$ HF_TOKEN=...
$ WANDB_API_KEY=...
$ WANDB_PROJECT=...
$ WANDB_NAME=axolotl-nvidia-llama-scout-train
$ HUB_MODEL_ID=...
$ dstack apply -f examples/fine-tuning/axolotl/.dstack.yml

 #  BACKEND              RESOURCES                     INSTANCE TYPE  PRICE     
 1  vastai (cz-czechia)  cpu=64 mem=128GB H100:80GB:2  18794506       $3.8907   
 2  vastai (us-texas)    cpu=52 mem=64GB  H100:80GB:2  20442365       $3.6926   
 3  vastai (fr-france)   cpu=64 mem=96GB  H100:80GB:2  20379984       $3.7389

Submit the run axolotl-nvidia-llama-scout-train? [y/n]:

Provisioning...
---> 100%
```

</div>

## Source code

The source-code of this example can be found in
[`examples/fine-tuning/axolotl` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/axolotl){:target="_blank"} and [`examples/distributed-training/axolotl` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/distributed-training/axolotl){:target="_blank"}.

## What's next?

1. Check [dev environments](https://dstack.ai/docs/dev-environments), [tasks](https://dstack.ai/docs/tasks), 
   [services](https://dstack.ai/docs/services), [clusters](https://dstack.ai/docs/guides/clusters) and [fleets](https://dstack.ai/docs/concepts/fleets).
2. See [AMD](https://dstack.ai/examples/accelerators/amd#axolotl). 
3. Browse [Axolotl :material-arrow-top-right-thin:{ .external }](https://github.com/OpenAccess-AI-Collective/axolotl){:target="_blank"}.
