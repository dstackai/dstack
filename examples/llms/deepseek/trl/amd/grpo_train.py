import argparse

from datasets import load_dataset
from transformers import AutoModelForCausalLM
from trl import GRPOConfig, GRPOTrainer


def parse_args():
    parser = argparse.ArgumentParser(description="Train a model using GRPOTrainer.")
    parser.add_argument(
        "--model_name_or_path",
        type=str,
        required=True,
        help="Path to the model or model identifier from huggingface.co/models",
    )
    parser.add_argument(
        "--dataset_name", type=str, required=True, help="Name of the dataset to use"
    )
    parser.add_argument(
        "--per_device_train_batch_size",
        type=int,
        default=1,
        help="Batch size per device for training",
    )
    parser.add_argument("--logging_steps", type=int, default=10, help="Logging steps interval")
    parser.add_argument(
        "--output_dir", type=str, default="output", help="Output directory for the trained model"
    )
    parser.add_argument(
        "--trust_remote_code", action="store_true", help="Trust remote code when loading the model"
    )
    return parser.parse_args()


def reward_len(completions, **kwargs):
    return [abs(20 - len(completion)) for completion in completions]


def main():
    args = parse_args()

    dataset = load_dataset(args.dataset_name, split="train")
    training_args = GRPOConfig(
        output_dir=args.output_dir,
        logging_steps=args.logging_steps,
        per_device_train_batch_size=args.per_device_train_batch_size,
    )

    model = AutoModelForCausalLM.from_pretrained(
        args.model_name_or_path, trust_remote_code=args.trust_remote_code
    )
    trainer = GRPOTrainer(
        model=model, reward_funcs=reward_len, args=training_args, train_dataset=dataset
    )

    trainer.train()


if __name__ == "__main__":
    main()
