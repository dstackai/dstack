import httpx2 as httpx

from dstack._internal.proxy.lib.errors import UnexpectedProxyError
from dstack._internal.proxy.lib.models import ChatModel
from dstack._internal.proxy.lib.services.model_proxy.clients.base import ChatCompletionsClient
from dstack._internal.proxy.lib.services.model_proxy.clients.tgi import TGIChatCompletions


def get_chat_client(model: ChatModel, http_client: httpx.AsyncClient) -> ChatCompletionsClient:
    if model.format_spec.format == "tgi":
        return TGIChatCompletions(
            http_client=http_client,
            chat_template=model.format_spec.chat_template,
            eos_token=model.format_spec.eos_token,
        )
    else:
        raise UnexpectedProxyError(f"Unsupported model format {model.format_spec.format}")
