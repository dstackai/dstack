from dstack._internal.core.models.backends.base import BackendType

BACKENDS_WITH_MULTINODE_SUPPORT = [
    BackendType.AWS,
    BackendType.AZURE,
    BackendType.GCP,
    BackendType.REMOTE,
]
BACKENDS_WITH_CREATE_INSTANCE_SUPPORT = [
    BackendType.AWS,
    BackendType.DSTACK,
    BackendType.AZURE,
    BackendType.CUDO,
    BackendType.DATACRUNCH,
    BackendType.GCP,
    BackendType.LAMBDA,
    BackendType.OCI,
    BackendType.TENSORDOCK,
]
BACKENDS_WITH_PRIVATE_GATEWAY_SUPPORT = [BackendType.AWS]
