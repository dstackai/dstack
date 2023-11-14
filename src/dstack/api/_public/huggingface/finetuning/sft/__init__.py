import os
import re
from typing import Any, Dict, Optional

from dstack._internal.core.models.configurations import TaskConfiguration
from dstack._internal.core.models.repos.virtual import VirtualRepo
from dstack.api._public.huggingface.finetuning import sft


class FineTuningTaskRepo(VirtualRepo):
    def __init__(self, repo_id: str):
        super().__init__(repo_id)
        self.add_file_from_package(package=sft, path="requirements.txt")
        self.add_file_from_package(package=sft, path="train.py")


class FineTuningTask(TaskConfiguration):
    """
    This task configuration loads a given model from the Hugging Face hub and fine-tunes it on the provided dataset
    (also from Hugging Face hub),
    utilizing the SFT and QLoRA techniques. The final model is pushed
    to Hugging Face hub.

    Args:
        model_name: The model that you want to train from the Hugging Face hub. E.g. gpt2, gpt2-xl, bert, etc.
        dataset_name: The instruction dataset to use.
        new_model_name: The name to use for pushing the fine-tuned model to the Hugging Face Hub. If unset, it defaults to the name of the run.
        env: The list of environment variables, e.g. `"HUGGING_FACE_HUB_TOKEN"`, `"WANDB_API_KEY"`, `"WANDB_PROJECT"`, etc.
        report_to: Supported integrations include `"wandb"` and `"tensorboard"`.
        per_device_train_batch_size: Batch size per GPU for training.
        per_device_eval_batch_size: Batch size per GPU for evaluation.
        gradient_accumulation_steps: Number of update steps to accumulate the gradients for.
        learning_rate: Initial learning rate (AdamW optimizer).
        max_grad_norm: Maximum gradient normal (gradient clipping).
        weight_decay: Weight decay to apply to all layers except bias/LayerNorm weights.
        lora_alpha: Alpha parameter for LoRA scaling.
        lora_dropout: Dropout probability for LoRA layers.
        lora_r: LoRA attention dimension.
        max_seq_length: Maximum sequence length to use.
        use_4bit: Activate 4bit precision base model loading.
        use_nested_quant: Activate nested quantization for 4bit base models.
        bnb_4bit_compute_dtype: Compute dtype for 4bit base models.
        bnb_4bit_quant_type: Quantization type fp4 or nf4.
        num_train_epochs: The number of training epochs for the reward model.
        fp16: Enables fp16 training.
        bf16: Enables bf16 training.
        packing: Use packing dataset creating.
        gradient_checkpointing: Enables gradient checkpointing.
        optim: The optimizer to use.
        lr_scheduler_type: Learning rate schedule. Constant a bit better than cosine, and has advantage for analysis
        max_steps: How many optimizer update steps to take
        warmup_ratio: Fraction of steps to do a warmup for
        group_by_length: Group sequences into batches with same length. Saves memory and speeds up training considerably.
        save_steps: Save checkpoint every X updates steps.
        logging_steps: Log every X updates steps.
    """

    def __init__(
        self,
        model_name: str,
        dataset_name: str,
        new_model_name: Optional[str] = None,
        env: Dict[str, str] = None,
        report_to: Optional[str] = None,
        per_device_train_batch_size: int = 4,
        per_device_eval_batch_size: int = 4,
        gradient_accumulation_steps: int = 1,
        learning_rate: float = 2e-4,
        max_grad_norm: float = 0.3,
        weight_decay: float = 0.001,
        lora_alpha: int = 16,
        lora_dropout: float = 0.1,
        lora_r: int = 64,
        max_seq_length: Optional[int] = None,
        use_4bit: bool = True,
        use_nested_quant: bool = True,
        bnb_4bit_compute_dtype: str = "float16",
        bnb_4bit_quant_type: str = "nf4",
        num_train_epochs: float = 1,
        fp16: bool = False,
        bf16: bool = False,
        packing: bool = False,
        gradient_checkpointing: bool = True,
        optim: str = "paged_adamw_32bit",
        lr_scheduler_type: str = "constant",
        max_steps: int = -1,
        warmup_ratio: float = 0.03,
        group_by_length: bool = True,
        save_steps: int = 0,
        logging_steps: int = 25,
    ):
        args = " ".join(
            [
                FineTuningTask._get_arg(t[0], t[1], t[2])
                for t in [
                    ("report_to", report_to, None),
                    ("per_device_train_batch_size", per_device_train_batch_size, 4),
                    ("per_device_eval_batch_size", per_device_eval_batch_size, 4),
                    ("gradient_accumulation_steps", gradient_accumulation_steps, 1),
                    ("learning_rate", learning_rate, 2e-4),
                    ("max_grad_norm", max_grad_norm, 0.3),
                    ("weight_decay", weight_decay, 0.001),
                    ("lora_alpha", lora_alpha, 16),
                    ("lora_dropout", lora_dropout, 0.1),
                    ("lora_r", lora_r, 64),
                    ("max_seq_length", max_seq_length, None),
                    ("use_4bit", use_4bit, True),
                    ("use_nested_quant", use_nested_quant, True),
                    ("bnb_4bit_compute_dtype", bnb_4bit_compute_dtype, "float16"),
                    ("bnb_4bit_quant_type", bnb_4bit_quant_type, "nf4"),
                    ("num_train_epochs", num_train_epochs, 1),
                    ("fp16", fp16, False),
                    ("bf16", bf16, False),
                    ("packing", packing, False),
                    ("gradient_checkpointing", gradient_checkpointing, True),
                    ("optim", optim, "paged_adamw_32bit"),
                    ("lr_scheduler_type", lr_scheduler_type, "constant"),
                    ("max_steps", max_steps, -1),
                    ("warmup_ratio", warmup_ratio, 0.03),
                    ("group_by_length", group_by_length, True),
                    ("save_steps", save_steps, 0),
                    ("logging_steps", logging_steps, 25),
                ]
            ]
        )
        # TODO: Support secrets
        # TODO: Support more integrations
        # Validating environment variables
        if "HUGGING_FACE_HUB_TOKEN" not in env:
            env["HUGGING_FACE_HUB_TOKEN"] = os.environ["HUGGING_FACE_HUB_TOKEN"]
        report_to_env = ""
        if report_to == "wandb":
            if "WANDB_API_KEY" not in env:
                env["WANDB_API_KEY"] = os.environ["WANDB_API_KEY"]
            if "WANDB_PROJECT" in os.environ:
                env["WANDB_PROJECT"] = os.environ["WANDB_PROJECT"]
            report_to_env += "WANDB_PROJECT=${WANDB_PROJECT:-$REPO_ID} WANDB_RUN_ID=$RUN_NAME"
        python_command = re.sub(
            " +",
            " ",
            f"{report_to_env} HF_HUB_ENABLE_HF_TRANSFER=1 python train.py --model_name {model_name} --new_model_name {new_model_name or '$RUN_NAME'} --dataset_name {dataset_name} --merge_and_push {args}",
        ).strip()
        pip_install_command = "pip install -r requirements.txt"
        commands = [pip_install_command]
        ports = []
        if report_to == "wandb":
            commands.append("pip install wandb")
        if report_to == "tensorboard":
            commands.append("pip install tensorboard")
            commands.append("tensorboard --logdir results/runs &")
            ports.append("6006")
        commands.append(python_command)
        super().__init__(commands=commands, ports=ports, env=env)

    @staticmethod
    def _get_arg(name, value: Any, default: Any) -> str:
        if value != default:
            return f"--{name} {str(value)}"
        else:
            return ""

    def get_repo(self) -> FineTuningTaskRepo:
        return FineTuningTaskRepo(repo_id="dstack.api._public.huggingface.finetuning.sft")
