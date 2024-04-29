from typing import Dict, Optional

import requests

from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.gateways import AnyModel


def complete_service_model(model_info: AnyModel, env: Dict[str, str]):
    if model_info.type == "chat" and model_info.format == "tgi":
        if model_info.chat_template is None or model_info.eos_token is None:
            hf_token = env.get("HUGGING_FACE_HUB_TOKEN", None)
            tokenizer_config = get_tokenizer_config(model_info.name, hf_token=hf_token)
            if model_info.chat_template is None:
                model_info.chat_template = tokenizer_config[
                    "chat_template"
                ]  # TODO(egor-s): default
            if model_info.eos_token is None:
                model_info.eos_token = tokenizer_config["eos_token"]  # TODO(egor-s): default
    elif model_info.type == "chat" and model_info.format == "openai":
        pass  # nothing to do


def get_tokenizer_config(model_id: str, hf_token: Optional[str] = None) -> dict:
    headers = {}
    if hf_token is not None:
        headers["Authorization"] = f"Bearer {hf_token}"
    try:
        resp = requests.get(
            f"https://huggingface.co/{model_id}/resolve/main/tokenizer_config.json",
            timeout=10,
            headers=headers,
        )
        if resp.status_code == 403:
            raise ServerClientError("Private HF models are not supported")
        if resp.status_code == 401:
            message = "Failed to access gated model. Specify HUGGING_FACE_HUB_TOKEN env."
            if hf_token is not None:
                message = "Failed to access gated model. Invalid HUGGING_FACE_HUB_TOKEN env."
            raise ServerClientError(message)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise ServerClientError(f"Failed to get tokenizer info: {e}")
    return resp.json()


def get_service_options(conf: ServiceConfiguration) -> dict:
    options = {}
    if conf.model is not None:
        complete_service_model(conf.model, env=conf.env)
        options["openai"] = {"model": conf.model.dict()}
    return options
