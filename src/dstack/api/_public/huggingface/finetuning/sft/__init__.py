import re
from typing import Any, Dict, Optional

from config import REPORT_TO_COMMANDS, REPORT_TO_PORTS

from dstack._internal.core.models.configurations import TaskConfiguration
from dstack._internal.core.models.repos.virtual import VirtualRepo
from dstack.api._public.huggingface.finetuning import sft


class SFTFineTuningTaskRepo(VirtualRepo):
    def __init__(self, repo_id: str):
        super().__init__(repo_id)
        self.add_file_from_package(package=sft, path="config.py")
        self.add_file_from_package(package=sft, path="requirements.txt")
        self.add_file_from_package(package=sft, path="train.py")


class SFTFineTuningTask(TaskConfiguration):
    """
    This task loads a given model from the Hugging Face hub and fine-tunes it on the provided dataset
    (also from Hugging Face hub),
    utilizing the SFT and QLoRA techniques. The final model is pushed
    to Hugging Face hub.

    Args:
        model_name: The model that you want to train from the Hugging Face hub. E.g. gpt2, gpt2-xl, bert, etc.
        dataset_name: The instruction dataset to use.
        new_model_name: The name to use for pushing the fine-tuned model to the Hugging Face Hub. If unset, it defaults to the name of the run.
        report_to: Supported integrations include `"wandb"` and `"tensorboard"`.
        env: The list of environment variables, which defaults to those of the current process.
            It must include `"HUGGING_FACE_HUB_TOKEN"` and related variables required by the integration specified in
            `report_to` (e.g., `"WANDB_API_KEY"`, `"WANDB_PROJECT"`, etc.)
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

    SUPPORTED_REPORT_TO = ["wandb", "tensorboard"]

    def __init__(
        self,
        model_name: str,
        dataset_name: str,
        env: Dict[str, str],
        new_model_name: Optional[str] = None,
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
        self._validate_env_vars(env, report_to)
        args = self._construct_args(
            {
                "report_to": (report_to, None),
                "per_device_train_batch_size": (per_device_train_batch_size, 4),
                "per_device_eval_batch_size": (per_device_eval_batch_size, 4),
                "gradient_accumulation_steps": (gradient_accumulation_steps, 1),
                "learning_rate": (learning_rate, 2e-4),
                "max_grad_norm": (max_grad_norm, 0.3),
                "weight_decay": (weight_decay, 0.001),
                "lora_alpha": (lora_alpha, 16),
                "lora_dropout": (lora_dropout, 0.1),
                "lora_r": (lora_r, 64),
                "max_seq_length": (max_seq_length, None),
                "use_4bit": (use_4bit, True),
                "use_nested_quant": (use_nested_quant, True),
                "bnb_4bit_compute_dtype": (bnb_4bit_compute_dtype, "float16"),
                "bnb_4bit_quant_type": (bnb_4bit_quant_type, "nf4"),
                "num_train_epochs": (num_train_epochs, 1),
                "fp16": (fp16, False),
                "bf16": (bf16, False),
                "packing": (packing, False),
                "gradient_checkpointing": (gradient_checkpointing, True),
                "optim": (optim, "paged_adamw_32bit"),
                "lr_scheduler_type": (lr_scheduler_type, "constant"),
                "max_steps": (max_steps, -1),
                "warmup_ratio": (warmup_ratio, 0.03),
                "group_by_length": (group_by_length, True),
                "save_steps": (save_steps, 0),
                "logging_steps": (logging_steps, 25),
            }
        )
        # TODO: Support secrets
        # TODO: Support more integrations
        # Validating environment variables
        report_to_env = self._setup_environment(report_to)
        python_command = re.sub(
            " +",
            " ",
            f"{report_to_env} HF_HUB_ENABLE_HF_TRANSFER=1 python train.py --model_name {model_name} --new_model_name {new_model_name or '$RUN_NAME'} --dataset_name {dataset_name} --merge_and_push {args}",
        ).strip()

        commands = ["pip install -r requirements.txt"]
        commands += REPORT_TO_COMMANDS.get(report_to, [])
        commands.append(python_command)

        ports = REPORT_TO_PORTS.get(report_to, [])
        super().__init__(commands=commands, ports=ports, env=env)

    def _validate_env_vars(self, env: Dict[str, str], report_to: str) -> None:
        """
        Validates the required environment variables based on the reporting tool.

        Args:
            env: The environment variables dictionary.
            report_to: The reporting tool name.

        Raises:
            ValueError: If required environment variables are not provided.
        """
        required_vars = ["HUGGING_FACE_HUB_TOKEN"]
        if report_to == "wandb":
            required_vars.append("WANDB_API_KEY")

        for var in required_vars:
            if var not in env:
                raise ValueError(f"{var} is required in environment variables.")

        if report_to not in self.SUPPORTED_REPORT_TO:
            raise ValueError(
                f"Unsupported value for report_to: {report_to}. Supported values are: {', '.join(self.SUPPORTED_REPORT_TO)}"
            )

    def _setup_environment(self, report_to: str) -> str:
        """
        Sets up the environment variables based on the reporting tool.

        Args:
            report_to: The reporting tool name.

        Returns:
            A string containing the set environment variables.
        """
        if report_to == "wandb":
            return "WANDB_PROJECT=${WANDB_PROJECT:-$REPO_ID} WANDB_RUN_ID=$RUN_NAME"
        return ""

    def _construct_args(self, arg_map: Dict[str, Any]) -> str:
        """
        Constructs the arguments string for the command.

        Args:
            arg_map: A dictionary containing argument names as keys and their values as values.

        Returns:
            A string containing the constructed arguments.
        """
        return " ".join(
            [self._get_arg(name, value[0], value[1]) for name, value in arg_map.items()]
        )

    @staticmethod
    def _get_arg(name, value: Any, default: Any) -> str:
        if value != default:
            return f"--{name} {str(value)}"
        else:
            return ""

    def get_repo(self) -> SFTFineTuningTaskRepo:
        return SFTFineTuningTaskRepo(repo_id="dstack.api._public.huggingface.finetuning.sft")
