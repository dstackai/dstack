from typing import List

from pydantic import BaseModel
from typing_extensions import Literal


class DstackConfigInfo(BaseModel):
    type: Literal["dstack"] = "dstack"
    base_backends: List[str]


class DstackBaseBackendConfigInfo(BaseModel):
    type: str


class DstackConfigValues(BaseModel):
    type: Literal["dstack"] = "dstack"
