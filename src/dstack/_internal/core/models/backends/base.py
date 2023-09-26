import enum
from typing import List

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


class ConfigMultiElement(BaseModel):
    selected: List[str] = []
    values: List[ConfigElementValue] = []
