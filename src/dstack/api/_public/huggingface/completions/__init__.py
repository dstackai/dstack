import os
from typing import Dict, Optional

from dstack._internal.core.models.configurations import ServiceConfiguration


class CompletionService(ServiceConfiguration):
    """
    This service configuration loads a given model from the Hugging Face hub
    and deploys it as a public endpoint.

    Args:
        model_name: The model that you want to deploy from the Hugging Face hub. E.g. gpt2, gpt2-xl, bert, etc.
        env: The list of environment variables, e.g. `"HUGGING_FACE_HUB_TOKEN"`, `"WANDB_API_KEY"`, `"WANDB_PROJECT"`, etc.
        quantize: Whether you want the model to be quantized. Supported values: `"awq"`, `"eetq"`, `"gptq"`, and `"bitsandbytes"`.
    """

    def __init__(
        self, model_name: str, env: Dict[str, str] = None, quantize: Optional[str] = None
    ):
        # TODO: Support secrets
        # Validating environment variables
        if not env:
            env = {}
        if "HUGGING_FACE_HUB_TOKEN" not in env and "HUGGING_FACE_HUB_TOKEN" in os.environ:
            env["HUGGING_FACE_HUB_TOKEN"] = os.environ["HUGGING_FACE_HUB_TOKEN"]
        if quantize and quantize not in ["awq", "eetq", "gptq", "bitsandbytes"]:
            raise ValueError(
                "The quantize argument can be one of the following: 'awq', 'eetq', 'gptq', or 'bitsandbytes'."
            )
        env["MODEL_ID"] = model_name
        launcher_command = (
            f"text-generation-launcher --hostname 0.0.0.0 --port 80 --trust-remote-code"
        )
        if quantize:
            launcher_command += f" --quantize {quantize}"
        super().__init__(
            commands=[launcher_command],
            image="ghcr.io/huggingface/text-generation-inference",
            port=80,
            env=env or None,
        )
