import enum
from typing import List, Optional

from dstack._internal.core.models.common import CoreModel


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
        RUNPOD (BackendType): Runpod Cloud
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
    OCI = "oci"
    RUNPOD = "runpod"
    TENSORDOCK = "tensordock"
    VASTAI = "vastai"


class ConfigElementValue(CoreModel):
    value: str
    label: str


class ConfigElement(CoreModel):
    selected: Optional[str] = None
    values: List[ConfigElementValue] = []


class ConfigMultiElement(CoreModel):
    selected: List[str] = []
    values: List[ConfigElementValue] = []
