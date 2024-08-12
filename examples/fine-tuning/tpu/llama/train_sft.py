from dataclasses import dataclass, field
from typing import Optional

from datasets import load_dataset
from optimum.tpu import AutoModelForCausalLM, fsdp_v2
from peft import LoraConfig
from transformers import AutoTokenizer, HfArgumentParser, TrainingArguments
from trl import SFTTrainer


@dataclass
class ScriptArguments:
    per_device_train_batch_size: Optional[int] = field(
        default=8, metadata={"help": "Batch size per device for training."}
    )
    per_device_eval_batch_size: Optional[int] = field(
        default=8, metadata={"help": "Batch size per device for evaluation."}
    )
    num_train_epochs: Optional[int] = field(
        default=1,
        metadata={"help": "The number of training epochs for the SFTTrainer."},
    )
    max_steps: int = field(
        default=-1, metadata={"help": "How many optimizer update steps to take"}
    )
    output_dir: str = field(
        default="./results",
        metadata={
            "help": "The output directory where the model predictions and checkpoints will be written."
        },
    )
    optim: Optional[str] = field(
        default="adafactor",
        metadata={"help": "The optimizer to use."},
    )
    dataset_name: Optional[str] = field(
        default="databricks/databricks-dolly-15k",
        metadata={"help": "The dataset to use."},
    )
    model_name: Optional[str] = field(
        default="meta-llama/Meta-Llama-3.1-8B",
        metadata={
            "help": "Only models Gemma 2B, Gemma 7B, Llama-2 7B and Llama-3 8B are tested with TPU v5e"
        },
    )
    lora_r: Optional[int] = field(default=8, metadata={"help": "LoRA attention dimension."})
    max_seq_length: Optional[int] = field(
        default=1024, metadata={"help": "Maximum sequence length to use."}
    )
    packing: Optional[bool] = field(
        default=True,
        metadata={"help": "Use packing dataset creating."},
    )
    push_to_hub: Optional[bool] = field(
        default=True,
        metadata={"help": "Push fined tuned model to hub."},
    )


def preprocess_function(sample):
    instruction = f"### Instruction\n{sample['instruction']}"
    context = f"### Context\n{sample['context']}" if len(sample["context"]) > 0 else None
    response = f"### Answer\n{sample['response']}"
    # join all the parts together
    prompt = "\n\n".join([i for i in [instruction, context, response] if i is not None])
    prompt += tokenizer.eos_token
    sample["prompt"] = prompt
    return sample


def create_and_prepare_model(args):
    model = AutoModelForCausalLM.from_pretrained(args.model_name, use_cache=False)
    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    return model, tokenizer


def create_and_prepare_trainer(model, dataset, args):
    data = dataset.map(preprocess_function, remove_columns=list(dataset.features))
    # For Testing purpose
    data = data.select(range(100))
    # Set up PEFT LoRA for fine-tuning.
    lora_config = LoraConfig(
        r=args.lora_r,
        target_modules=["k_proj", "v_proj"],
        task_type="CAUSAL_LM",
    )

    # Set up the FSDP arguments
    fsdp_training_args = fsdp_v2.get_fsdp_training_args(model)

    # Set up the trainer
    trainer = SFTTrainer(
        model=model,
        train_dataset=data,
        args=TrainingArguments(
            per_device_train_batch_size=args.per_device_train_batch_size,
            num_train_epochs=args.num_train_epochs,
            max_steps=args.max_steps,
            output_dir=args.output_dir,
            optim=args.optim,
            logging_steps=1,
            dataloader_drop_last=True,  # Required for FSDPv2.
            **fsdp_training_args,
        ),
        peft_config=lora_config,
        dataset_text_field="prompt",
        max_seq_length=args.max_seq_length,
        packing=args.packing,
    )

    return trainer


def parse_config() -> ScriptArguments:
    import sys

    import yaml

    # Ensure a YAML file is provided as an argument
    if len(sys.argv) != 2:
        sys.exit(1)

    config_path = sys.argv[1]

    # Read the YAML file
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # Parse arguments using HfArgumentParser
    parser = HfArgumentParser(ScriptArguments)
    script_args = parser.parse_dict(config)[0]
    return script_args


if __name__ == "__main__":
    args = parse_config()
    fsdp_v2.use_fsdp_v2()
    dataset = load_dataset(args.dataset_name, split="train")
    model, tokenizer = create_and_prepare_model(args)
    trainer = create_and_prepare_trainer(model, dataset, args)
    trainer.train()
    if args.push_to_hub:
        kwargs = {
            "finetuned_from": args.model_name,
            "dataset": args.dataset_name,
        }
        trainer.push_to_hub(**kwargs)
