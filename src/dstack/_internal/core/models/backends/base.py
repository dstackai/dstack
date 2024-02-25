import enum
from typing import List, Optional

from pydantic import BaseModel


class BackendType(str, enum.Enum):
    """
    Attributes:
        AWS (BackendType): Amazon Web Services
        AZURE (BackendType): Microsoft Azure
        CUDO (BackendType): Cudo
        DSTACK (BackendType): dstack Sky
        GCP (BackendType): Google Cloud Platform
        DATACRUNCH (BackendType): DataCrunch
        KUBERNETES (BackendType): Kubernetes
        LAMBDA (BackendType): Lambda Cloud
        TENSORDOCK (BackendType): TensorDock Marketplace
        VASTAI (BackendType): Vast.ai Marketplace
    """

    AWS = "aws"
    AZURE = "azure"
    CUDO = "cudo"
    DATACRUNCH = "datacrunch"
    DSTACK = "dstack"
    GCP = "gcp"
    KUBERNETES = "kubernetes"
    LAMBDA = "lambda"
    LOCAL = "local"
    REMOTE = "remote"  # TODO: replace for LOCAL
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
