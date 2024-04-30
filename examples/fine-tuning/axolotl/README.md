# Axolotl

[`axolotl`](https://github.com/OpenAccess-AI-Collective/axolotl) streamlines the fine-tuning of AI models, offering support for multiple configurations and architectures.

Furthermore, `axolotl` provides a set of [`yaml` examples](https://github.com/OpenAccess-AI-Collective/axolotl/tree/main/examples) for almost all kinds of LLMs such as LLaMA2 family, Gemma family, LLaMA3 family, Jamba, and so on. It's recommended to navigate through the examples to get a sense about the role of each parameters, and adjust them for your specific use cases. Also, it is worth checking out all configs/parameters options with a brief description from [this doc](https://github.com/OpenAccess-AI-Collective/axolotl/blob/main/docs/config.qmd).

The example below replicates the [FSDP+QLoRA on LLaMA3 70B](https://github.com/OpenAccess-AI-Collective/axolotl/blob/main/examples/llama-3/qlora-fsdp-70b.yaml), except that here we use Llama3 8B. You can see the [`config.yaml`](config.yaml).

## Running with `dstack`

Running `axolotl` with `dstack` is very straightforward.

First, define the [`train.dstack.yaml`](train.dstack.yaml) task configuration file as follows:

```yaml
type: task

image: winglian/axolotl-cloud:main-20240429-py3.11-cu121-2.2.1

env:
  - HUGGING_FACE_HUB_TOKEN
  - WANDB_API_KEY

commands:
  - accelerate launch -m axolotl.cli.train config.yaml

ports:
  - 6006

resources:
  gpu:
    memory: 24GB..
    count: 2
```

> [!NOTE]
> Feel free to adjust `resources` to specify the required resources.

We are using the official Docker image provided by Axolotl team (`winglian/axolotl-cloud:main-20240429-py3.11-cu121-2.2.1`). If you want to see other images, their official [repo](https://hub.docker.com/r/winglian/axolotl-cloud/tags). Note, `dstack` requires the CUDA driver to be 12.1+.

To run the task, use the following command:

```shell
HUGGING_FACE_HUB_TOKEN=<...> \
WANDB_API_KEY=<...> \
dstack run . -f examples/fine-tuning/axolotl/train.dstack.yaml
```

To push the final fine-tuned model to Hugging Face Hub, set `hub_model_id` in [`config.yaml`](config.yaml).

### Building `axolotl` from sources

If you'd like to build `axolot` from sources (e.g. if you intend to modify its source code), follow its [installation guide](https://github.com/OpenAccess-AI-Collective/axolotl?tab=readme-ov-file#condapip-venv).

Example:

```yaml
type: task

python: 3.11

env:
  - HUGGING_FACE_HUB_TOKEN
  - WANDB_API_KEY

commands:
  - conda install cuda
  - pip3 install torch torchvision torchaudio

  - git clone https://github.com/OpenAccess-AI-Collective/axolotl.git
  - cd axolotl

  - pip3 install packaging
  - pip3 install -e '.[flash-attn,deepspeed]'
    
  - accelerate launch -m axolotl.cli.train ../config.yaml

ports:
  - 6006

resources:
  gpu:
    memory: 24GB..
    count: 2
```
