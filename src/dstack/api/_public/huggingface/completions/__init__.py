import os
from typing import Dict, List, Optional, Tuple

from dstack._internal.core.models.configurations import ServiceConfiguration, TaskConfiguration


def get_configuration(
    model_name: str,
    env: Optional[Dict[str, str]] = None,
    quantize: Optional[str] = None,
    dtype: Optional[str] = None,
) -> Tuple[List[str], str, int, Optional[Dict[str, str]]]:
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
    launcher_command = "text-generation-launcher --hostname 0.0.0.0 --port 80 --trust-remote-code"
    if quantize:
        launcher_command += f" --quantize {quantize}"
    if dtype:
        launcher_command += f" --dtype {dtype}"
    image = "ghcr.io/huggingface/text-generation-inference"
    port = 80
    return [launcher_command], image, port, env or None


class CompletionService(ServiceConfiguration):
    """
    This service configuration loads a given model from the Hugging Face hub
    and deploys it as a public endpoint.

    Args:
        model_name: The model that you want to deploy from the Hugging Face hub. E.g. gpt2, gpt2-xl, bert, etc.
        env: The list of environment variables, e.g. `"HUGGING_FACE_HUB_TOKEN"`, `"WANDB_API_KEY"`, `"WANDB_PROJECT"`, etc.
        quantize: Whether you want the model to be quantized. Supported values: `"awq"`, `"eetq"`, `"gptq"`, and `"bitsandbytes"`.
        dtype: The dtype to be forced upon the model. This option cannot be used with `quantize`.
    """

    def __init__(
        self,
        model_name: str,
        env: Dict[str, str] = None,
        quantize: Optional[str] = None,
        dtype: Optional[str] = None,
    ):
        commands, image, port, env = get_configuration(model_name, env, quantize, dtype)
        super().__init__(commands=commands, image=image, port=port, env=env)


class CompletionTask(TaskConfiguration):
    """
    This task configuration loads a specified model from the Hugging Face hub and runs it as a private endpoint while
    forwarding the port to the local machine.

    Args:
        model_name: The model that you want to deploy from the Hugging Face hub. E.g. gpt2, gpt2-xl, bert, etc.
        env: The list of environment variables, e.g. `"HUGGING_FACE_HUB_TOKEN"`, `"WANDB_API_KEY"`, `"WANDB_PROJECT"`, etc.
        quantize: Whether you want the model to be quantized. Supported values: `"awq"`, `"eetq"`, `"gptq"`, and `"bitsandbytes"`.
        dtype: The dtype to be forced upon the model. This option cannot be used with `quantize`.
        local_port: The local port to forward the traffic to.
    """

    def __init__(
        self,
        model_name: str,
        env: Dict[str, str] = None,
        quantize: Optional[str] = None,
        dtype: Optional[str] = None,
        local_port: int = 80,
    ):
        commands, image, port, env = get_configuration(model_name, env, quantize, dtype)
        super().__init__(
            commands=commands,
            image=image,
            ports=[f"{local_port}:{port}"],
            env=env,
        )
