from pydantic.fields import Field
from typing_extensions import Annotated, List, Literal, Optional, Union

from dstack._internal.core.models.backends.base import ConfigMultiElement
from dstack._internal.core.models.common import CoreModel


class DataCrunchConfigInfo(CoreModel):
    type: Literal["datacrunch"] = "datacrunch"
    regions: Optional[List[str]] = None


class DataCrunchAPIKeyCreds(CoreModel):
    type: Annotated[Literal["api_key"], Field(description="The type of credentials")] = "api_key"
    client_id: Annotated[str, Field(description="The client ID")]
    client_secret: Annotated[str, Field(description="The client secret")]


AnyDataCrunchCreds = DataCrunchAPIKeyCreds


DataCrunchCreds = AnyDataCrunchCreds


class DataCrunchConfigInfoWithCreds(DataCrunchConfigInfo):
    creds: AnyDataCrunchCreds


AnyDataCrunchConfigInfo = Union[DataCrunchConfigInfo, DataCrunchConfigInfoWithCreds]


class DataCrunchConfigInfoWithCredsPartial(CoreModel):
    type: Literal["datacrunch"] = "datacrunch"
    creds: Optional[AnyDataCrunchCreds]
    regions: Optional[List[str]]


class DataCrunchConfigValues(CoreModel):
    type: Literal["datacrunch"] = "datacrunch"
    regions: Optional[ConfigMultiElement]


class DataCrunchStoredConfig(DataCrunchConfigInfo):
    pass
