"""
Data structures related to `type: service` runs.
"""

from typing import Optional, Union

from pydantic import Field
from typing_extensions import Annotated, Literal

from dstack._internal.core.models.common import CoreModel


class BaseChatModel(CoreModel):
    type: Annotated[Literal["chat"], Field(description="The type of the model")] = "chat"
    name: Annotated[str, Field(description="The name of the model")]
    format: Annotated[
        str, Field(description="The serving format. Supported values include `openai` and `tgi`")
    ]


class TGIChatModel(BaseChatModel):
    """
    Mapping of the model for the OpenAI-compatible endpoint.

    Attributes:
        type (str): The type of the model, e.g. "chat"
        name (str): The name of the model. This name will be used both to load model configuration from the HuggingFace Hub and in the OpenAI-compatible endpoint.
        format (str): The format of the model, e.g. "tgi" if the model is served with HuggingFace's Text Generation Inference.
        chat_template (Optional[str]): The custom prompt template for the model. If not specified, the default prompt template from the HuggingFace Hub configuration will be used.
        eos_token (Optional[str]): The custom end of sentence token. If not specified, the default end of sentence token from the HuggingFace Hub configuration will be used.
    """

    format: Annotated[
        Literal["tgi"], Field(description="The serving format. Must be set to `tgi`")
    ]
    chat_template: Annotated[
        Optional[str],
        Field(
            description=(
                "The custom prompt template for the model."
                " If not specified, the default prompt template"
                " from the HuggingFace Hub configuration will be used"
            )
        ),
    ] = None  # will be set before registering the service
    eos_token: Annotated[
        Optional[str],
        Field(
            description=(
                "The custom end of sentence token."
                " If not specified, the default end of sentence token"
                " from the HuggingFace Hub configuration will be used"
            )
        ),
    ] = None


class OpenAIChatModel(BaseChatModel):
    """
    Mapping of the model for the OpenAI-compatible endpoint.

    Attributes:
        type (str): The type of the model, e.g. "chat"
        name (str): The name of the model. This name will be used both to load model configuration from the HuggingFace Hub and in the OpenAI-compatible endpoint.
        format (str): The format of the model, i.e. "openai".
        prefix (str): The `base_url` prefix: `http://hostname/{prefix}/chat/completions`. Defaults to `/v1`.
    """

    format: Annotated[
        Literal["openai"], Field(description="The serving format. Must be set to `openai`")
    ]
    prefix: Annotated[str, Field(description="The `base_url` prefix (after hostname)")] = "/v1"


ChatModel = Annotated[Union[TGIChatModel, OpenAIChatModel], Field(discriminator="format")]
AnyModel = Union[ChatModel]  # embeddings and etc.
