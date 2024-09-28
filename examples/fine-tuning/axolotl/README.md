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

<div editor-title="examples/fine-tuning/axolotl/train.dstack.yml">

```yaml
type: task
name: axolotl-train

# Using the official Axolotl's Docker image
image: winglian/axolotl-cloud:main-20240429-py3.11-cu121-2.2.1

# Required environment variables
env:
  - HUGGING_FACE_HUB_TOKEN
  - WANDB_API_KEY
# Commands of the task
commands:
  - accelerate launch -m axolotl.cli.train examples/fine-tuning/axolotl/config.yaml

# Use spot or on-demand instances
spot_policy: auto

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
$ HUGGING_FACE_HUB_TOKEN=...
$ WANDB_API_KEY=...
$ dstack apply -f examples/fine-tuning/axolotl/train.dstack.yml
```

</div>

## Fleets

> By default, `dstack run` reuses `idle` instances from one of the existing [fleets](https://dstack.ai/docs/concepts/fleets).
> If no `idle` instances meet the requirements, it creates a new fleet using one of the configured backends.

The example folder includes a fleet configuration: 
[ `examples/fine-tuning/axolotl/fleet.dstack.yml` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/axolotl/fleet.dstack.yml){:target="_blank"}
(a single node with a `24GB` GPU).

You can update the fleet configuration to change the vRAM size, GPU model, number of GPUs per node, or number of nodes. 

A fleet can be provisioned with `dstack apply`:

<div class="termy">

```shell
dstack apply -f examples/fine-tuning/axolotl/fleet.dstack.yml
```

</div>

Once provisioned, the fleet can run dev environments and fine-tuning tasks.
To delete the fleet, use `dstack fleet delete`.

> To ensure `dstack apply` always reuses an existing fleet,
> pass `--reuse` to `dstack apply` (or set `creation_policy` to `reuse` in the task configuration).
> The default policy is `reuse_or_create`.

## Dev environment

If you'd like to play with the example using a dev environment, run
[`.dstack.yml` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/examples/fine-tuning/axolotl/.dstack.yml){:target="_blank"} via `dstack apply`:

<div class="termy">

```shell
$ HUGGING_FACE_HUB_TOKEN=...
$ WANDB_API_KEY=...
$ dstack apply -f examples/fine-tuning/axolotl/.dstack.yaml 
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
