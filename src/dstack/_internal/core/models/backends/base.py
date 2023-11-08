import enum
from typing import List, Optional

from pydantic import BaseModel


class BackendType(str, enum.Enum):
    AWS = "aws"
    AZURE = "azure"
    DSTACK = "dstack"
    GCP = "gcp"
    LAMBDA = "lambda"
    LOCAL = "local"
    NEBIUS = "nebius"
    TENSORDOCK = "tensordock"
    VASTAI = "vastai"


class ConfigElementValue(BaseModel):
    value: str
    label: str


class ConfigElement(BaseModel):
    selected: Optional[str] = None
    values: List[ConfigElementValue] = []


class ConfigMultiElement(BaseModel):
    selected: List[str] = []
    values: List[ConfigElementValue] = []
