from datetime import datetime
from enum import Enum
from typing import Optional

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel


class OwnerType(str, Enum):
    INSTANCE = "instance"
    # TODO: VOLUME, GATEWAY, PLACEMENT_GROUP


class OrphanCleanupMode(str, Enum):
    REPORT = "report"
    DELETE = "delete"


class ListedResourceGroup(CoreModel):
    """
    Resources provisioned as one backend method call:
    the server-level resource (e.g. instance) and the backend-internal resources
    created with it (e.g. disks, keys, scripts, NICs).
    """

    backend: BackendType
    owner_type: OwnerType
    provider_ref: str
    """dstack's `provider_ref` of the owner resources read from a tag or a name."""
    primary_id: Optional[str]
    """Provider's id of the owner resource (e.g.`JobProvisioningData.instance_id` for the instances).
    `None` if the group has only internal resources left.
    """
    region: Optional[str]
    created_at: datetime
    description: str
    """Human-readable summary for events and logs"""
    backend_data: Optional[str]
    """Everything the backend needs to delete the group. Opaque to the server."""
