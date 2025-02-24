from datetime import timedelta

from dstack._internal.core.models.backends.base import BackendType


def get_provisioning_timeout(backend_type: BackendType, instance_type_name: str) -> timedelta:
    """
    This timeout is used in a few places, but roughly refers to the max time between
    requesting instance creation and the instance becoming ready to accept jobs.
    For container-based backends, this also includes the image pulling time.
    """
    if backend_type == BackendType.LAMBDA:
        return timedelta(minutes=30)
    if backend_type == BackendType.RUNPOD:
        return timedelta(minutes=20)
    if backend_type == BackendType.KUBERNETES:
        return timedelta(minutes=20)
    if backend_type == BackendType.OCI and instance_type_name.startswith("BM."):
        return timedelta(minutes=20)
    if backend_type == BackendType.VULTR and instance_type_name.startswith("vbm"):
        return timedelta(minutes=55)
    return timedelta(minutes=10)
