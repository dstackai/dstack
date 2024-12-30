from typing import List, Optional

from pydantic.fields import Field
from typing_extensions import Annotated, Literal

from dstack._internal.core.models.backends.base import ConfigElement, ConfigMultiElement
from dstack._internal.core.models.common import CoreModel


class VultrConfigInfo(CoreModel):
    type: Literal["vultr"] = "vultr"
    project_id: str
    regions: Optional[List[str]] = None


class VultrStoredConfig(VultrConfigInfo):
    pass


class VultrAPIKeyCreds(CoreModel):
    type: Annotated[Literal["api_key"], Field(description="The type of credentials")] = "api_key"
    api_key: Annotated[str, Field(description="The API key")]


AnyVultrCreds = VultrAPIKeyCreds
VultrCreds = AnyVultrCreds


class VultrConfigInfoWithCreds(VultrConfigInfo):
    creds: AnyVultrCreds


class VultrConfigInfoWithCredsPartial(CoreModel):
    type: Literal["vultr"] = "vultr"
    creds: Optional[AnyVultrCreds]
    project_id: Optional[str]
    regions: Optional[List[str]]


class VultrConfigValues(CoreModel):
    type: Literal["vultr"] = "vultr"
    regions: Optional[ConfigMultiElement]
    project_id: Optional[ConfigElement]
