# Axolotl

[Axolotl](https://github.com/OpenAccess-AI-Collective/axolotl) streamlines the fine-tuning of AI models It not only
supports multiple configurations and architectures but also provides many
ready-to-use [recipes](https://github.com/axolotl-ai-cloud/axolotl/tree/main/examples). You just need to pick a suitable
recipe and adjust it for your use case.

> This example shows how use Axolotl with `dstack` to fine-tune Llama3 8B using FSDP and QLoRA
> on one node.

## Prerequisites

Once `dstack` is [installed](https://dstack.ai/docs/installation), clone the repo and run `dstack init`:

```shell
git clone https://github.com/dstackai/dstack
cd dstack
dstack init
```

## Training configuration recipe

Axolotl reads the model, LoRA, and dataset arguments, as well as trainer configuration from a YAML file. This file can
be found at [`examples/fine-tuning/axolotl/config.yaml`](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/axolotl/config.yaml).
You can modify it as needed.

> Before you proceed with training, make sure to update the `hub_model_id` in [`examples/fine-tuning/axolotl/config.yaml`](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/alignment-handbook/config.yaml)
> with your HuggingFace username.

## Single-node training

The easiest way to run a training script with `dstack` is by creating a task configuration file.
This file can be found at [`examples/fine-tuning/axolotl/train.dstack.yml`](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/axolotl/train.dstack.yml). Below is its content: 

```yaml
type: task
# The name is optional, if not specified, generated randomly
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

resources:
  gpu:
    # 24GB or more vRAM
    memory: 24GB..
    # Two or more GPU
    count: 2..
```

The task uses Axolotl's Docker image, where Axolotl is already pre-installed.

To run the task, use `dstack apply`:

```shell
HUGGING_FACE_HUB_TOKEN=...
WANDB_API_KEY=...

dstack apply -f examples/fine-tuning/axolotl/train.dstack.yml
```

## Fleets

> By default, `dstack run` reuses `idle` instances from one of the existing [fleets](https://dstack.ai/docs/fleets).
> If no `idle` instances meet the requirements, it creates a new fleet using one of the configured backends.

The example folder includes a fleet configuration: 
[ `examples/fine-tuning/axolotl/fleet.dstack.yml`](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/axolotl/fleet.dstack.yml) 
( a single node with a `24GB` GPU).

You can update the fleet configuration to change the vRAM size, GPU model, number of GPUs per node, or number of nodes. 

A fleet can be provisioned with `dstack apply`:

```shell
dstack apply -f examples/fine-tuning/axolotl/fleet.dstack.yml
```

Once provisioned, the fleet can run dev environments and fine-tuning tasks.
To delete the fleet, use `dstack fleet delete`.

> To ensure `dstack apply` always reuses an existing fleet,
> pass `--reuse` to `dstack apply` (or set `creation_policy` to `reuse` in the task configuration).
> The default policy is `reuse_or_create`.

## Dev environment

If you'd like to play with the example using a dev environment, run
[.dstack.yml](https://github.com/dstackai/dstack/examples/fine-tuning/axolotl/.dstack.yml) via `dstack apply`:

```shell
dstack apply -f examples/fine-tuning/axolotl/.dstack.yaml 
```

## Source code

The source-code of this example can be found in  [`https://github.com/dstackai/dstack/examples/fine-tuning/axolotl`](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/axolotl).

## Contributing

Find a mistake or can't find an important example? Raise an [issue](https://github.com/dstackai/dstack/issues) or send a [pull request](https://github.com/dstackai/dstack/tree/master/examples)!

## What's next?

1. Browse [Axolotl](https://github.com/OpenAccess-AI-Collective/axolotl).
2. Check [dev environments](https://dstack.ai/docs/dev-environments), [tasks](https://dstack.ai/docs/tasks), 
   [services](https://dstack.ai/docs/services), and [fleets](https://dstack.ai/docs/fleets).
3. See other [examples](https://github.com/dstackai/dstack/blob/master/examples/).