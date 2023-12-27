from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.configurations import ModelInfo


def complete_model(model_info: ModelInfo) -> dict:
    model_info = model_info.copy(deep=True)
    # TODO(egor-s): support more types and formats
    # TODO(egor-s): get tokenizer_info.json from HF for chat/tgi
    # https://huggingface.co/{model_info.name}/resolve/main/tokenizer_config.json
    if model_info.chat_template is None:
        raise ConfigurationError("Currently `chat_template` is required for `chat` models")
    if model_info.eos_token is None:
        raise ConfigurationError("Currently `eos_token` is required for `chat` models")
    return {"model": model_info.dict()}
