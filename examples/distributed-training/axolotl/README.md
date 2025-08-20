# Axolotl

This example walks you through how to run distributed fine-tune using [Axolotl :material-arrow-top-right-thin:{ .external }](https://github.com/axolotl-ai-cloud/axolotl){:target="_blank"} with `dstack`.

??? info "Prerequisites"
    Once `dstack` is [installed](https://dstack.ai/docs/installation), clone the repo with examples.

    <div class="termy">
 
    ```shell
    $ git clone https://github.com/dstackai/dstack
    $ cd dstack
    ```
    </div>

## Create a fleet

Before submitting distributed training runs, make sure to create a fleet with a `placement` set to `cluster`.

> For more detials on how to use clusters with `dstack`, check the [Clusters](https://dstack.ai/docs/guides/clusters) guide.

## Define a configuration

Once the fleet is created, define a distributed task configuration. Here's an example of distributed `QLORA` task using `FSDP`.

<div editor-title="examples/distributed-training/axolotl/.dstack.yml">

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

### Apply the configuration

To run a configuration, use the [`dstack apply`](https://dstack.ai/docs/reference/cli/dstack/apply.md) command.

<div class="termy">

```shell
$ HF_TOKEN=...
$ WANDB_API_KEY=...
$ WANDB_PROJECT=...
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
[`examples/distributed-training/axolotl` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/distributed-training/axolotl).

!!! info "What's next?"
    1. Read the [clusters](https://dstack.ai/docs/guides/clusters) guide
    2. Check [dev environments](https://dstack.ai/docs/dev-environments), [tasks](https://dstack.ai/docs/concepts/tasks),
       [services](https://dstack.ai/docs/concepts/services), and [fleets](https://dstack.ai/docs/concepts/fleets)
