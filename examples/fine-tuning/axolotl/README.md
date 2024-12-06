# Axolotl

This example shows how use [Axolotl :material-arrow-top-right-thin:{ .external }](https://github.com/OpenAccess-AI-Collective/axolotl){:target="_blank"} 
with `dstack` to fine-tune Llama3 8B using FSDP and QLoRA.

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

Axolotl reads the model, LoRA, and dataset arguments, as well as trainer configuration from a YAML file. This file can
be found at [`examples/fine-tuning/axolotl/config.yaml` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/axolotl/config.yaml){:target="_blank"}.
You can modify it as needed.

> Before you proceed with training, make sure to update the `hub_model_id` in [`examples/fine-tuning/axolotl/config.yaml` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/alignment-handbook/config.yaml){:target="_blank"}
> with your HuggingFace username.

## Single-node training

The easiest way to run a training script with `dstack` is by creating a task configuration file.
This file can be found at [`examples/fine-tuning/axolotl/train.dstack.yml` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/axolotl/train.dstack.yml){:target="_blank"}.

<div editor-title="examples/fine-tuning/axolotl/.dstack.yml">

```yaml
type: task
name: axolotl-train

# Using the official Axolotl's Docker image
image: winglian/axolotl-cloud:main-20240429-py3.11-cu121-2.2.1

# Required environment variables
env:
  - HF_TOKEN
  - WANDB_API_KEY
# Commands of the task
commands:
  - accelerate launch -m axolotl.cli.train examples/fine-tuning/axolotl/config.yaml

# Uncomment to leverage spot instances
#spot_policy: auto

resources:
  gpu:
    # 24GB or more vRAM
    memory: 24GB..
    # Two or more GPU
    count: 2..
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
