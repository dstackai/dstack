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

For instance, if you want to QLoRA fine-tune Gemma 7B model on your own SFT dataset hosted on Hugging Face Hub, you can
prepare a `yaml` config file as [config.yaml](config.yaml). This config is based on the Zephyr-7B-Gemma recipe except
the following modification:

- `dataset_mixer` field to point which SFT dataset to be used.
- `hub_model_id` and `output_dir` fields to point where the model and its checkpoints should be saved.
- `LoRA arguments` related fields to indicate that this fine-tuning is based on QLoRA methodology.

With the `config.yaml` file configured, you can run the following command to QLoRA fine-tune Gemma 7B model on 2
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

First, define the [`train.dstack.yaml`](train.dstack.yaml) task configuration file as following:

```yaml
type: task

python: "3.11"

env:
  - HUGGING_FACE_HUB_TOKEN
  - WANDB_API_KEY

commands:
  - conda install cuda
  - git clone https://github.com/huggingface/alignment-handbook.git
  - mkdir -p alignment-handbook/recipes/custom/
  - cp config.yaml alignment-handbook/recipes/custom/config.yaml

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

The task clones the `huggingface/alignment-handbook` repo, and copies our local `config.yaml` to the recipies subfolder.
Then, the task installs dependencies, and launches the recipe.

Our `config.yaml` sets `report_to` to `wandb` and `tensorboard`. That's why we the task also installs `wandb`.

To run the task, use the following command:

```shell
HUGGING_FACE_HUB_TOKEN=<...> \
WANDB_API_KEY=<...> \
dstack run . -f examples/fine-tuning/alignment-handbook/train.dstack.yaml
```

## Results

- [merged_ds_coding](https://huggingface.co/datasets/chansung/merged_ds_coding): SFT dataset for solely coding task. It roughly contains 60k training dataset.
- [chansung/coding_llamaduo_60k_v0.2](https://huggingface.co/chansung/coding_llamaduo_60k_v0.2): QLoRA adapter for Gemma 7B with the exactly the same configuration as in [`config.yaml`](./config.yaml). This adapter is fine-tuned on the `merged_ds_coding` dataset with 2xA6000 GPUs via `dstack` Sky.