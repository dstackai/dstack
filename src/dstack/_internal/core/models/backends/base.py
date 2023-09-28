import enum
from typing import List, Optional

from pydantic import BaseModel


class BackendType(str, enum.Enum):
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
    LAMBDA = "lambda"
    LOCAL = "local"


class ConfigElementValue(BaseModel):
    value: str
    label: str


class ConfigElement(BaseModel):
    selected: Optional[str] = None
    values: List[ConfigElementValue] = []


class ConfigMultiElement(BaseModel):
    selected: List[str] = []
    values: List[ConfigElementValue] = []
