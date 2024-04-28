# Alignment Handbook

Alignment Handbook provides robust recipes to continue pretraining and to align language models with human and AI preferences. It basically comes with two types of recipes and four types of scripts that were used to create Hugging Face [Zephyr models](https://huggingface.co/HuggingFaceH4):

- Accelerate recipes: configurations for [DeepSpeed Zero3](https://huggingface.co/docs/accelerate/v0.11.0/en/deepspeed), [FSDP(Fully Sharded Data Parallel)](https://pytorch.org/tutorials/intermediate/FSDP_tutorial.html), and Multi GPUs.

- Training recipes: configurations of how GPT2, StarChat2-15B, Zephyr-141B-A35B, Zephyr-7B-Beta, and Zephyr-7B-Gemma models were fine-tuned. 

- Scripts: [`run_cpt.py`](https://github.com/huggingface/alignment-handbook/blob/main/scripts/run_cpt.py) for continual pre-training, [`run_sft.py`](https://github.com/huggingface/alignment-handbook/blob/main/scripts/run_sft.py) for supervised fine-tuning, [`run_dpo.py`](https://github.com/huggingface/alignment-handbook/blob/main/scripts/run_dpo.py) for aligning with preferences via [DPO](https://arxiv.org/abs/2305.18290), and [`run_orpo.py`](https://github.com/huggingface/alignment-handbook/blob/main/scripts/run_orpo.py) aligning with [ORPO](https://arxiv.org/abs/2403.07691).

## Alignment Handbook on dstack

Alignment Handbook provides all the code base you need to run CPT, SFT, DPO, and ORPO within Hugging Face OSS ecosystem such as `transformers`, `peft`, `accelerate`, `trl`. All you need to do is to modify recipes for accelerate and training, and run appropriate script. 

For instance, if you want to QLoRA fine-tune Gemma 7B model on your own SFT dataset hosted on Hugging Face Hub, you can prepare a `yaml` config file as [config.yaml](./config.yaml). This config is based on the Zephyr-7B-Gemma recipe except the following modification:
- `dataset_mixer` field to point which SFT dataset to be used.
- `hub_model_id` and `output_dir` fields to point where the model and its checkpoints should be saved.
- `LoRA arguments` related fields to indicate that this fine-tuning is based on QLoRA methodology.

