from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import Field
from typing_extensions import Annotated

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.resources import Memory


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
        Field(
            description="The volume ID. Must be specified only for registering existing volumes"
        ),
    ] = None


class Volume(CoreModel):
    name: str
    configuration: VolumeConfiguration
    created_at: datetime
    status: VolumeStatus
    status_message: Optional[str] = None
    volume_id: Optional[str] = None


class VolumeComputeConfiguration(CoreModel):
    name: str
    project_name: str
    backend: BackendType
    region: str
    size_gb: Optional[int] = None
    volume_id: Optional[str] = None


class VolumeProvisioningData(CoreModel):
    volume_id: str
    size_gb: int
    availability_zone: Optional[str] = None
    backend_data: Optional[str] = None  # backend-specific data in json
