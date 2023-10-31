from pydantic import BaseModel, Field
from typing_extensions import Literal


class DstackConfigInfo(BaseModel):
    type: Literal["dstack"] = "dstack"


class DstackConfigValues(BaseModel):
    type: Literal["dstack"] = "dstack"
