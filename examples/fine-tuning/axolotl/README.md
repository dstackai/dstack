# Axolotl

[Axolotl](https://github.com/OpenAccess-AI-Collective/axolotl) is a tool designed to streamline the fine-tuning of various AI models, offering support for multiple configurations and architectures. By configuring lots of different fine-tuning parameters in a single `yaml` file, we can simply leverage the scripts to launch fine-tuning workloads based on the `yaml` file. 

Furthermore, axolotl provides a set of [`yaml` examples](https://github.com/OpenAccess-AI-Collective/axolotl/tree/main/examples) for almost all kinds of LLMs such as LLaMA2 family, Gemma family, LLaMA3 family, Jamba, and so on. It is strongly recommended to navigate through the examples, get a sense about the role of each parameters, and adjust them for your specific use cases. Also, it is worth checking out all configs/parameters options with brief description from [this doc](https://github.com/OpenAccess-AI-Collective/axolotl/blob/main/docs/config.qmd).

For this example, we reuse the [example of FSDP+QLoRA on LLaMA3 70B](https://github.com/OpenAccess-AI-Collective/axolotl/blob/main/examples/llama-3/qlora-fsdp-70b.yaml). Instead of 70B variant of LLaMA3, we chose to use 8B for the sake of keeping this example simple. Check out the modified [`config.yaml`](./config.yaml).
- [FSDP+QLoRA](https://www.answer.ai/posts/2024-03-06-fsdp-qlora.html) allows us to apply QLoRA technique to fine-tune a LLM on multiple GPUs. This technique was first introduced by [Answer.AI](https://www.answer.ai/), and it was adopted by Hugging Face's OSS ecosystem (`transformers`, `peft`, `trl`, `acclerate`).

## Axolotl on dstack

It is super easy to launch axolotl's fine-tuning workload. You just need to remember a single command, `accelerate launch -m axolotl.cli.train config.yaml`. For instance, below [`train.dstack.yaml`](./train.dstack.yaml) shows a concrete example of running that command on dstack cloud.

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

- `winglian/axolotl-cloud:main-20240429-py3.11-cu121-2.2.1` is the base Docker image that dstack will use to provision a VM. This is one kind of official Docker images provided by Axolotl team. If you want to find out other version options of Python and CUDA, you can naviage available Docker images [here](https://hub.docker.com/r/winglian/axolotl-cloud/tags).

- `HUGGING_FACE_HUB_TOKEN` should be set as environment variable so that the fine-tuned model and its checkpoints could be pushed to the Hugging Face Hub (for downloading gated models and private datasets as well). Besides that, `WANDB_API_KEY` is for logging into [Weights and Biases](https://wandb.ai/) to record training process.
  - Furthermore, if you want to save the final fine-tuned model on Hugging Face Hub, you should set `hub_model_id` field inside the `config.yaml`.

- There is a single command, `accelerate launch -m axolotl.cli.train config.yaml` which launch the fine-tuning job. By default, it leverages all the available GPUs on a system, but if you want to explicitly specify the number of GPUs to be used, you can simply set `--num_processes=...` option.

- This example is based on FSDP+QLoRA fine-tuning, so we have chosen two GPUs (*24GB.. means any GPU whose memory is equal to or greater than 24GB*). 

Now, simply run the `dstack run` command as below:

```console
$ HUGGING_FACE_HUB_TOKEN=<YOUR-HF-ACCESS-TOKEN> \
WANDB_API_KEY=<YOUR-W&B-API-KEY> \
dstack run . -f train.dstack.yaml --spot -d
```

If you fine-tune LLMs with standard methodologies, this example should cover enough. However, if you are about to modify axolotl's code base to meet your specific use cases, consider [following the instructions of manual installation](https://github.com/OpenAccess-AI-Collective/axolotl?tab=readme-ov-file#condapip-venv). It should be as simple as something like below:

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

## Conclusion

We have gone through a very simple example about how to run axolotl's LLM fine-tuning on dstack based on axolotl's official Docker image and manual installation. `dstack` allows us to easily provision GPU infrastructure with few lines of code, so we could spend more time on thinking about fine-tuning experiments. 