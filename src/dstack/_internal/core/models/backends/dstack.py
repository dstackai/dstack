from pydantic import BaseModel
from typing_extensions import Literal


class DstackConfigInfo(BaseModel):
    type: Literal["dstack"] = "dstack"


class DstackConfigValues(BaseModel):
    type: Literal["dstack"] = "dstack"
