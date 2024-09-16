from datasets import load_dataset
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
from trl import SFTTrainer

# Base model and tokenizer names.
base_model_name = "meta-llama/Meta-Llama-3.1-8B"

# Load base model to GPU memory.
device = "cuda:0"
base_model = AutoModelForCausalLM.from_pretrained(base_model_name, trust_remote_code=True).to(
    device
)

# Load tokenizer.
tokenizer = AutoTokenizer.from_pretrained(base_model_name, trust_remote_code=True)
tokenizer.pad_token = tokenizer.eos_token
tokenizer.padding_side = "right"

# Dataset for fine-tuning.
training_dataset_name = "mlabonne/guanaco-llama2-1k"
training_dataset = load_dataset(training_dataset_name, split="train")


# Training parameters for SFTTrainer.
training_arguments = TrainingArguments(
    output_dir="./results",
    num_train_epochs=1,
    per_device_train_batch_size=4,
    gradient_accumulation_steps=1,
    optim="paged_adamw_32bit",
    save_steps=50,
    logging_steps=50,
    learning_rate=4e-5,
    weight_decay=0.001,
    fp16=False,
    bf16=False,
    max_grad_norm=0.3,
    max_steps=-1,
    warmup_ratio=0.03,
    group_by_length=True,
    lr_scheduler_type="constant",
    report_to="tensorboard",
)

peft_config = LoraConfig(lora_alpha=16, lora_dropout=0.1, r=64, bias="none", task_type="CAUSAL_LM")
peft_model = get_peft_model(base_model, peft_config)
peft_model.print_trainable_parameters()

# Initialize an SFT trainer.
sft_trainer = SFTTrainer(
    model=base_model,
    train_dataset=training_dataset,
    peft_config=peft_config,
    dataset_text_field="text",
    tokenizer=tokenizer,
    args=training_arguments,
)

# Run the trainer.
sft_trainer.train()
