from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field

from dstack._internal.core.models.instances import SSHConnectionParams
from dstack._internal.proxy.lib.models import RateLimit


class BaseChatModel(BaseModel):
    type: Literal["chat"]
    name: str
    format: str


class TGIChatModel(BaseChatModel):
    format: Literal["tgi"]
    chat_template: str
    eos_token: str


class OpenAIChatModel(BaseChatModel):
    format: Literal["openai"]
    prefix: str


ChatModel = Annotated[Union[TGIChatModel, OpenAIChatModel], Field(discriminator="format")]
AnyModel = Union[ChatModel]  # embeddings and etc.


class OpenAIOptions(BaseModel):
    model: AnyModel


class Options(BaseModel):
    openai: Optional[OpenAIOptions] = None


class RegisterServiceRequest(BaseModel):
    run_name: str
    domain: str
    https: bool
    auth: bool
    client_max_body_size: int
    options: Options
    ssh_private_key: str
    rate_limits: tuple[RateLimit, ...] = ()


class RegisterReplicaRequest(BaseModel):
    job_id: str
    app_port: int
    ssh_host: str
    ssh_port: int
    ssh_proxy: Optional[SSHConnectionParams]
    ssh_head_proxy: Optional[SSHConnectionParams]
    ssh_head_proxy_private_key: Optional[str]


class RegisterEntrypointRequest(BaseModel):
    domain: str
    https: bool
