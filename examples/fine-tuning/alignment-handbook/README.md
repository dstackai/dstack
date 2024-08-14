# Alignment Handbook

[Alignment Handbook](https://github.com/huggingface/alignment-handbook) provides robust recipes to continue pretraining
and to align language models with human and AI preferences. It basically comes with two types of recipes and four types
of scripts that were used to create Hugging Face [Zephyr models](https://huggingface.co/HuggingFaceH4):

- Accelerate recipes: configurations for [DeepSpeed Zero3](https://huggingface.co/docs/accelerate/v0.11.0/en/deepspeed),
- [FSDP(Fully Sharded Data Parallel)](https://pytorch.org/tutorials/intermediate/FSDP_tutorial.html), and multi GPU.

- Training recipes: configurations of how GPT2, StarChat2-15B, Zephyr-141B-A35B, Zephyr-7B-Beta, and Zephyr-7B-Gemma
  models were fine-tuned.

- Scripts: [`run_cpt.py`](https://github.com/huggingface/alignment-handbook/blob/main/scripts/run_cpt.py) for continual
  pre-training, [`run_sft.py`](https://github.com/huggingface/alignment-handbook/blob/main/scripts/run_sft.py) for
  supervised fine-tuning, [`run_dpo.py`](https://github.com/huggingface/alignment-handbook/blob/main/scripts/run_dpo.py)
  for aligning with preferences via [DPO](https://arxiv.org/abs/2305.18290),
  and [`run_orpo.py`](https://github.com/huggingface/alignment-handbook/blob/main/scripts/run_orpo.py) aligning
  with [ORPO](https://arxiv.org/abs/2403.07691).

## Basics

Alignment Handbook provides all the code you need to run CPT, SFT, DPO, and ORPO within Hugging Face OSS ecosystem
such as `transformers`, `peft`, `accelerate`, `trl`. All you need to do is to modify recipes for accelerate and
training, and run appropriate script.

For instance, if you want to QLoRA fine-tune LLaMA3.1 8B model on your own SFT dataset hosted on Hugging Face Hub, you can
prepare a `yaml` config file as [config.yaml](llama3.1_8b/config.yaml). This config is based on the Zephyr-7B-Gemma recipe 
except the following modification:

- `tokenizer_name_or_path` field to leverage the tokenizer used in LLaMA3.1 instruct models.
- `chat_template` field to employ [OpenAI's ChatML template](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/chat-markup-language) instead of the official [LLaMA3.1 instruct prompt template](https://llama.meta.com/docs/model-cards-and-prompt-formats/llama3_1/).
- `dataset_mixer` field to point which SFT dataset to be used.
- `hub_model_id` and `output_dir` fields to point where the model and its checkpoints should be saved.
- `LoRA arguments` related fields to indicate that this fine-tuning is based on QLoRA methodology.

> [!NOTE]
> Feel free to use the official LLaMA3.1 instruct prompt template. As of writing this tutorial, ChatML template was chosen becuase I found it works much better on my experiments by observing train/loss metrics over time.

With the `config.yaml` file configured, you can run the following command to QLoRA fine-tune an LLM model on 2
GPUs:

```shell
ACCELERATE_LOG_LEVEL=info accelerate launch \
  --config_file config.yaml \
  --num_processes=2 \
  scripts/run_sft.py \
  recipes/{model_name}/{task}/config_qlora.yaml
```

For more details and other alignment methods, please check out the
alignment-handbook's [official repository](https://github.com/huggingface/alignment-handbook).

## Running via `dstack`

This example demonstrate how to run an Alignment Handbook recipe via `dstack`.

First, define the [`train.dstack.yaml`](llama3.1_8b/train.dstack.yaml) task configuration file as following:

```yaml
type: task

python: "3.11"

env:
  - HUGGING_FACE_HUB_TOKEN
  - WANDB_API_KEY

commands:
  - conda install cuda
  - git clone https://github.com/deep-diver/alignment-handbook.git
  - mkdir -p alignment-handbook/recipes/custom/
  - cp llama3.1_8b/config.yaml alignment-handbook/recipes/custom/config.yaml

  - cd alignment-handbook
  - python -m pip install .
  - python -m pip install flash-attn --no-build-isolation

  - pip install wandb
  - wandb login $WANDB_API_KEY

  - ACCELERATE_LOG_LEVEL=info accelerate launch
    --config_file recipes/accelerate_configs/multi_gpu.yaml
    --num_processes=$DSTACK_GPUS_NUM
    scripts/run_sft.py
    recipes/custom/config.yaml
    
ports:
  - 6006
  
resources:
  gpu:
    memory: 40GB
    name: A6000
    count: 2
```

> [!NOTE]
> Feel free to adjust `resources` to specify the required resources.

> [!NOTE]
> This tutorial uses [the fork](https://github.com/deep-diver/alignment-handbook.git) of the official [Alignment Handbook repository](https://github.com/huggingface/alignment-handbook) which contains the fixes of a bug that blocks running SFT with the current version of `transformers`. This tutorial will be updated when the [PR of the fixes](https://github.com/huggingface/alignment-handbook/pull/191) gets merged into the main branch.

The task clones the `huggingface/alignment-handbook` repo, and copies our local `config.yaml` to the recipies subfolder.
Then, the task installs dependencies, and launches the recipe.

Our `config.yaml` sets `report_to` to `wandb` and `tensorboard`. That's why we the task also installs `wandb`.

To run the task, use the following command:

```shell
HUGGING_FACE_HUB_TOKEN=<...> \
WANDB_API_KEY=<...> \
dstack run . -f train.dstack.yaml
```

## Resources

- [gemma7b](gemma7b): Alignment Handbook recipe for fine-tuning Gemma 7B model and dstack's Task yaml file.
- [merged_ds_coding](https://huggingface.co/datasets/chansung/merged_ds_coding): SFT dataset for solely coding task. It roughly contains 60k training dataset.
- [chansung/coding_llamaduo_60k_v0.2](https://huggingface.co/chansung/coding_llamaduo_60k_v0.2): QLoRA adapter for Gemma 7B with the exactly the same configuration as in [`config.yaml`](./config.yaml). This adapter is fine-tuned on the `merged_ds_coding` dataset with 2xA6000 GPUs via `dstack` Sky.