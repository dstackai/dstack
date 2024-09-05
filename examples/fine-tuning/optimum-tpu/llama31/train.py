from dataclasses import dataclass, field
from typing import Optional

from datasets import load_dataset
from optimum.tpu import AutoModelForCausalLM, fsdp_v2
from peft import LoraConfig, TaskType, get_peft_model
from transformers import (
    AutoTokenizer,
    DataCollatorForLanguageModeling,
    HfArgumentParser,
    Trainer,
    TrainingArguments,
)


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
        default="Abirate/english_quotes",
        metadata={"help": "The dataset to use."},
    )
    model_name: Optional[str] = field(
        default="meta-llama/Meta-Llama-3.1-8B",
        metadata={
            "help": "Only models Gemma 2B, Gemma 7B, Llama-2 7B and Llama-3 8B Llama-3.1 8B are tested with TPU v5e"
        },
    )
    lora_r: Optional[int] = field(default=4, metadata={"help": "LoRA attention dimension."})
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


def create_and_prepare_model(args):
    base_model = AutoModelForCausalLM.from_pretrained(args.model_name)
    lora_config = LoraConfig(
        r=args.lora_r,  # the dimension of the low-rank matrices
        lora_alpha=8,  # scaling factor for LoRA activations vs pre-trained weight activations
        lora_dropout=0.05,
        bias="none",
        inference_mode=False,
        task_type=TaskType.CAUSAL_LM,
        target_modules=["o_proj", "v_proj"],
    )  #

    model = get_peft_model(base_model, lora_config)
    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    # Add custom token for padding Llama
    tokenizer.add_special_tokens({"pad_token": tokenizer.eos_token})
    return model, tokenizer


def create_and_prepare_trainer(model, tokenizer, dataset, args):
    data = dataset.map(lambda samples: tokenizer(samples["quote"]), batched=True)
    fsdp_training_args = fsdp_v2.get_fsdp_training_args(model)

    trainer = Trainer(
        model=model,
        train_dataset=data["train"],
        args=TrainingArguments(
            per_device_train_batch_size=args.per_device_train_batch_size,
            num_train_epochs=args.num_train_epochs,
            max_steps=args.max_steps,
            output_dir=args.output_dir,
            optim=args.optim,
            logging_steps=1,
            dataloader_drop_last=True,  # Required by FSDP v2 and SPMD.
            **fsdp_training_args,
        ),
        data_collator=DataCollatorForLanguageModeling(tokenizer, mlm=False),
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
    dataset = load_dataset(args.dataset_name)
    model, tokenizer = create_and_prepare_model(args)
    trainer = create_and_prepare_trainer(model, tokenizer, dataset, args)
    trainer.train()
    if args.push_to_hub:
        kwargs = {
            "finetuned_from": args.model_name,
            "dataset": args.dataset_name,
        }
        trainer.push_to_hub(**kwargs)
