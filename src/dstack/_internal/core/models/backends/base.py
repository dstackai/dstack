import enum


class BackendType(str, enum.Enum):
    """
    Attributes:
        AMDDEVCLOUD (BackendType): AMD Developer Cloud
        AWS (BackendType): Amazon Web Services
        AZURE (BackendType): Microsoft Azure
        CLOUDRIFT (BackendType): CloudRift
        CUDO (BackendType): Cudo
        DATACRUNCH (BackendType): DataCrunch (for backward compatibility)
        DIGITALOCEAN (BackendType): DigitalOcean
        DSTACK (BackendType): dstack Sky
        GCP (BackendType): Google Cloud Platform
        HOTAISLE (BackendType): Hot Aisle
        KUBERNETES (BackendType): Kubernetes
        LAMBDA (BackendType): Lambda Cloud
        NEBIUS (BackendType): Nebius AI Cloud
        OCI (BackendType): Oracle Cloud Infrastructure
        RUNPOD (BackendType): Runpod Cloud
        TENSORDOCK (BackendType): TensorDock Marketplace
        VASTAI (BackendType): Vast.ai Marketplace
        VERDA (BackendType): Verda Cloud
        VULTR (BackendType): Vultr
    """

    AMDDEVCLOUD = "amddevcloud"
    AWS = "aws"
    AZURE = "azure"
    CLOUDRIFT = "cloudrift"
    CUDO = "cudo"
    DATACRUNCH = "datacrunch"  # BackendType for backward compatibility
    DIGITALOCEAN = "digitalocean"
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
    VERDA = "verda"
    VULTR = "vultr"
