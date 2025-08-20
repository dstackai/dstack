# Axolotl

This example shows how to use [Axolotl :material-arrow-top-right-thin:{ .external }](https://github.com/OpenAccess-AI-Collective/axolotl){:target="_blank"} with `dstack` to fine-tune 4-bit Quantized `Llama-4-Scout-17B-16E` using SFT with FSDP and QLoRA.

??? info "Prerequisites"
    Once `dstack` is [installed](https://dstack.ai/docs/installation), clone the repo with examples.

    <div class="termy">
 
    ```shell
    $ git clone https://github.com/dstackai/dstack
    $ cd dstack
    ```
 
    </div>

## Define a configuration

Axolotl reads the model, QLoRA, and dataset arguments, as well as trainer configuration from a [`scout-qlora-flexattn-fsdp2.yaml` :material-arrow-top-right-thin:{ .external }](https://github.com/axolotl-ai-cloud/axolotl/blob/main/examples/llama-4/scout-qlora-flexattn-fsdp2.yaml){:target="_blank"} file. The configuration uses 4-bit axolotl quantized version of `meta-llama/Llama-4-Scout-17B-16E`, requiring only ~43GB VRAM/GPU with 4K context length.

Below is a task configuration that does fine-tuning.

<div editor-title="examples/single-node-training/axolotl/.dstack.yml">

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
    The example above uses NVIDIA accelerators. To use it with AMD, check out [AMD](https://dstack.ai/examples/accelerators/amd#axolotl).

## Run the configuration

Once the configuration is ready, run `dstack apply -f <configuration file>`, and `dstack` will automatically provision the
cloud resources and run the configuration.

<div class="termy">

```shell
$ HF_TOKEN=...
$ WANDB_API_KEY=...
$ WANDB_PROJECT=...
$ HUB_MODEL_ID=...
$ dstack apply -f examples/single-node-training/axolotl/.dstack.yml

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
[`examples/single-node-training/axolotl` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/single-node-training/axolotl){:target="_blank"} and [`examples/distributed-training/axolotl` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/distributed-training/axolotl){:target="_blank"}.

## What's next?

1. Browse the [Axolotl distributed training](https://dstack.ai/docs/examples/distributed-training/axolotl) example
2. Check [dev environments](https://dstack.ai/docs/dev-environments), [tasks](https://dstack.ai/docs/tasks),
   [services](https://dstack.ai/docs/services), [fleets](https://dstack.ai/docs/concepts/fleets)
3. See the [AMD](https://dstack.ai/examples/accelerators/amd#axolotl) example
