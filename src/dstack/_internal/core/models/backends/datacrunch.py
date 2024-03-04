from typing import List, Optional, Union

from typing_extensions import Literal

from dstack._internal.core.models.backends.base import ConfigMultiElement
from dstack._internal.core.models.common import CoreModel


class DataCrunchConfigInfo(CoreModel):
    type: Literal["datacrunch"] = "datacrunch"
    regions: Optional[List[str]] = None


class DataCrunchAPIKeyCreds(CoreModel):
    type: Literal["api_key"] = "api_key"
    client_id: str
    client_secret: str


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
