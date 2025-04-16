# Axolotl

This example shows how use [Axolotl :material-arrow-top-right-thin:{ .external }](https://github.com/OpenAccess-AI-Collective/axolotl){:target="_blank"} 
with `dstack` to fine-tune 4-bit Quantized [Llama-4-Scout-17B-16E :material-arrow-top-right-thin:{ .external }](https://huggingface.co/axolotl-quants/Llama-4-Scout-17B-16E-Linearized-bnb-nf4-bf16){:target="_blank"} using FSDP and QLoRA.

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
```

</div>

## Source code

The source-code of this example can be found in
[`examples/fine-tuning/axolotl` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/axolotl){:target="_blank"}.

## What's next?

1. Check [dev environments](https://dstack.ai/docs/dev-environments), [tasks](https://dstack.ai/docs/tasks), 
   [services](https://dstack.ai/docs/services), and [fleets](https://dstack.ai/docs/concepts/fleets).
2. See [AMD](https://dstack.ai/examples/accelerators/amd#axolotl). 
3. Browse [Axolotl :material-arrow-top-right-thin:{ .external }](https://github.com/OpenAccess-AI-Collective/axolotl){:target="_blank"}.
