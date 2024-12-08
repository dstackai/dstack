import uuid
from datetime import datetime
from enum import Enum
from pathlib import PurePosixPath
from typing import List, Literal, Optional, Tuple, Union

from pydantic import Field, validator
from typing_extensions import Annotated, Self

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


class VolumeSpec(CoreModel):
    configuration: VolumeConfiguration
    configuration_path: Optional[str] = None


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
    # Default user to "" for client backward compatibility (old 0.18 servers).
    # TODO: Remove in 0.19
    user: str = ""
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


class VolumePlan(CoreModel):
    project_name: str
    user: str
    spec: VolumeSpec
    current_resource: Optional[Volume]


def _split_mount_point(mount_point: str) -> Tuple[str, str]:
    parts = mount_point.split(":")
    if len(parts) != 2:
        raise ValueError(f"invalid mount point format: {mount_point}")
    src, dest = parts
    return src, dest


def _validate_mount_point_path(path: str) -> str:
    if not path:
        raise ValueError("empty path")
    _path = PurePosixPath(path)
    if not _path.is_absolute():
        raise ValueError(f"path must be absolute: {path}")
    if ".." in _path.parts:
        raise ValueError(f".. are not allowed: {path}")
    return str(_path)


class VolumeMountPoint(CoreModel):
    name: Annotated[
        Union[str, List[str]],
        Field(
            description=(
                "The network volume name or the list of network volume names to mount."
                " If a list is specified, one of the volumes in the list will be mounted."
                " Specify volumes from different backends/regions to increase availability."
            )
        ),
    ]
    path: Annotated[str, Field(description="The absolute container path to mount the volume at")]

    _validate_path = validator("path", allow_reuse=True)(_validate_mount_point_path)

    @classmethod
    def parse(cls, v: str) -> Self:
        name, path = _split_mount_point(v)
        return cls(name=name, path=path)


class InstanceMountPoint(CoreModel):
    instance_path: Annotated[str, Field(description="The absolute path on the instance (host)")]
    path: Annotated[str, Field(description="The absolute path in the container")]

    _validate_instance_path = validator("instance_path", allow_reuse=True)(
        _validate_mount_point_path
    )
    _validate_path = validator("path", allow_reuse=True)(_validate_mount_point_path)

    @classmethod
    def parse(cls, v: str) -> Self:
        instance_path, path = _split_mount_point(v)
        return cls(instance_path=instance_path, path=path)


MountPoint = Union[VolumeMountPoint, InstanceMountPoint]


def parse_mount_point(v: str) -> MountPoint:
    src, dest = _split_mount_point(v)
    if "/" in src:
        return InstanceMountPoint(instance_path=src, path=dest)
    return VolumeMountPoint(name=src, path=dest)
