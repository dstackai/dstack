import uuid
from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import Field
from typing_extensions import Annotated

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.resources import Memory
from dstack._internal.utils.common import get_or_error


class VolumeStatus(str, Enum):
    SUBMITTED = "submitted"
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    FAILED = "failed"


class VolumeConfiguration(CoreModel):
    type: Literal["volume"] = "volume"
    name: Annotated[Optional[str], Field(description="The volume name")] = None
    backend: Annotated[BackendType, Field(description="The volume backend")]
    region: Annotated[str, Field(description="The volume region")]
    size: Annotated[
        Optional[Memory],
        Field(description="The volume size. Must be specified when creating new volumes"),
    ] = None
    volume_id: Annotated[
        Optional[str],
        Field(description="The volume ID. Must be specified when registering external volumes"),
    ] = None

    @property
    def size_gb(self) -> int:
        return int(get_or_error(self.size))


class VolumeProvisioningData(CoreModel):
    backend: Optional[BackendType] = None
    volume_id: str
    size_gb: int
    availability_zone: Optional[str] = None
    # price per month
    price: Optional[float] = None
    # should be manually attached/detached
    attachable: bool = True
    detachable: bool = True
    backend_data: Optional[str] = None  # backend-specific data in json


class VolumeAttachmentData(CoreModel):
    device_name: Optional[str] = None


class Volume(CoreModel):
    id: uuid.UUID
    name: str
    project_name: str
    configuration: VolumeConfiguration
    external: bool
    created_at: datetime
    status: VolumeStatus
    status_message: Optional[str] = None
    deleted: bool
    volume_id: Optional[str] = None  # id of the volume in the cloud
    provisioning_data: Optional[VolumeProvisioningData] = None
    attachment_data: Optional[VolumeAttachmentData] = None


class VolumeMountPoint(CoreModel):
    name: Annotated[str, Field(description="The name of the volume to mount")]
    path: Annotated[str, Field(description="The container path to mount the volume at")]
