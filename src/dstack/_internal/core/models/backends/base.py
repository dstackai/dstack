import enum


class BackendType(str, enum.Enum):
    """
    Attributes:
        AWS (BackendType): Amazon Web Services
        AZURE (BackendType): Microsoft Azure
        CLOUDRIFT (BackendType): CloudRift
        CUDO (BackendType): Cudo
        DSTACK (BackendType): dstack Sky
        GCP (BackendType): Google Cloud Platform
        DATACRUNCH (BackendType): DataCrunch
        HOTAISLE (BackendType): Hot Aisle
        KUBERNETES (BackendType): Kubernetes
        LAMBDA (BackendType): Lambda Cloud
        NEBIUS (BackendType): Nebius AI Cloud
        OCI (BackendType): Oracle Cloud Infrastructure
        RUNPOD (BackendType): Runpod Cloud
        TENSORDOCK (BackendType): TensorDock Marketplace
        VASTAI (BackendType): Vast.ai Marketplace
        VULTR (BackendType): Vultr
    """

    AWS = "aws"
    AZURE = "azure"
    CLOUDRIFT = "cloudrift"
    CUDO = "cudo"
    DATACRUNCH = "datacrunch"
    DSTACK = "dstack"
    GCP = "gcp"
    HOTAISLE = "hotaisle"
    KUBERNETES = "kubernetes"
    LAMBDA = "lambda"
    LOCAL = "local"
    REMOTE = "remote"  # TODO: replace for LOCAL
    NEBIUS = "nebius"
    OCI = "oci"
    RUNPOD = "runpod"
    TENSORDOCK = "tensordock"
    VASTAI = "vastai"
    VULTR = "vultr"
