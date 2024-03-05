import requests

from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.gateways import AnyModel


def complete_service_model(model_info: AnyModel):
    model_info = model_info.copy(deep=True)
    if model_info.type == "chat" and model_info.format == "tgi":
        if model_info.chat_template is None or model_info.eos_token is None:
            tokenizer_config = get_tokenizer_config(model_info.name)
            if model_info.chat_template is None:
                model_info.chat_template = tokenizer_config[
                    "chat_template"
                ]  # TODO(egor-s): default
            if model_info.eos_token is None:
                model_info.eos_token = tokenizer_config["eos_token"]  # TODO(egor-s): default
    elif model_info.type == "chat" and model_info.format == "openai":
        pass  # nothing to do


def get_tokenizer_config(model_id: str) -> dict:
    try:
        resp = requests.get(
            f"https://huggingface.co/{model_id}/resolve/main/tokenizer_config.json"
        )
        if resp.status_code == 403:
            raise ConfigurationError("Private HF models are not supported")
        resp.raise_for_status()
    except requests.RequestException as e:
        raise ConfigurationError(f"Failed to get tokenizer info: {e}")
    return resp.json()


def get_service_options(conf: ServiceConfiguration) -> dict:
    options = {}
    if conf.model is not None:
        complete_service_model(conf.model)
        options["openai"] = {"model": conf.model.dict()}
    return options
