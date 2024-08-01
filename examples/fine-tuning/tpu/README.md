# Finetune Gemma with TPU

This example shows how to Finetune `Gemma-2B` model on TPU [v5e](https://cloud.google.com/tpu/docs/v5e) using [🤗Hugging Face Optimum TPU](https://github.com/huggingface/optimum-tpu) with `dstack`. 
It also leverages HuggingFace's libraries like `peft` and `trl`.

## Prerequisites

Before following this tutorial, ensure you've [installed](https://dstack.ai/docs/installation) `dstack`.

## Training configuration recipe

`dstack`'s [training script](train.py) reads the model, LoRA and dataset arguments, as well as trainer configuration from YAML file.
This file can be found at [examples/fine-tuning/tpu/config.yaml](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/tpu/config.yaml). 
You can modify it as needed.

## Training

The easiest way to run a training script with `dstack` is by creating a task configuration file.
This file can be found at [examples/fine-tuning/tpu/train.dstack.yml](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/tpu/train.dstack.yml).
Below is its content:
```yaml
type: task

python: "3.11"

env:
  - HUGGING_FACE_HUB_TOKEN

commands:
  - git clone https://github.com/huggingface/optimum-tpu.git
  - mkdir -p optimum-tpu/examples/custom/
  - cp examples/fine-tuning/tpu/train.py optimum-tpu/examples/custom/train.py
  - cp examples/fine-tuning/tpu/config.yaml optimum-tpu/examples/custom/config.yaml
  - cd optimum-tpu
  - pip install -e . -f https://storage.googleapis.com/libtpu-releases/index.html
  - pip install trl peft
  - python examples/custom/train.py examples/custom/config.yaml

ports:
  - 6006

resources:
  gpu: tpu-v5litepod-8
```
The task clones Optimum-tpu's repo, installs the dependencies, and runs the script.

To run the task, use dstack apply:
```shell
HUGGING_FACE_HUB_TOKEN=...

dstack apply -f examples/fine-tuning/tpu/train.dstack.yml
```
## Dev environment

If you'd like to play with the example using a dev environment, run
[.dstack.yml](.dstack.yml) via `dstack apply`:

```shell
HUGGING_FACE_HUB_TOKEN=...

dstack apply -f examples/fine-tuning/tpu/.dstack.yml
```

## Source code

The source-code of this example can be found in  [`https://github.com/dstackai/dstack/examples/fine-tuning/tpu`](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/tpu).

## Contributing

Find a mistake or can't find an important example? Raise an [issue](https://github.com/dstackai/dstack/issues) or send a [pull request](https://github.com/dstackai/dstack/tree/master/examples)!

## What's next?

1. Browse [Optimum-TPU](https://github.com/huggingface/optimum-tpu).
2. Check [dev environments](https://dstack.ai/docs/dev-environments), [tasks](https://dstack.ai/docs/tasks), 
   [services](https://dstack.ai/docs/services).
3. See other [TPU Inference](https://github.com/dstackai/dstack/blob/master/examples/tpu/tgi).