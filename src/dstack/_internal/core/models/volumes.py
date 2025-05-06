import uuid
from datetime import datetime
from enum import Enum
from pathlib import PurePosixPath
from typing import Dict, List, Literal, Optional, Tuple, Union

from pydantic import Field, validator
from typing_extensions import Annotated, Self

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.resources import Memory
from dstack._internal.utils.common import get_or_error
from dstack._internal.utils.tags import tags_validator


class VolumeStatus(str, Enum):
    SUBMITTED = "submitted"
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    FAILED = "failed"

    def is_active(self) -> bool:
        return self not in self.finished_statuses()

    @classmethod
    def finished_statuses(cls) -> List["VolumeStatus"]:
        return [cls.FAILED]


class VolumeConfiguration(CoreModel):
    type: Literal["volume"] = "volume"
    name: Annotated[Optional[str], Field(description="The volume name")] = None
    backend: Annotated[BackendType, Field(description="The volume backend")]
    region: Annotated[str, Field(description="The volume region")]
    availability_zone: Annotated[
        Optional[str], Field(description="The volume availability zone")
    ] = None
    size: Annotated[
        Optional[Memory],
        Field(description="The volume size. Must be specified when creating new volumes"),
    ] = None
    volume_id: Annotated[
        Optional[str],
        Field(description="The volume ID. Must be specified when registering external volumes"),
    ] = None
    tags: Annotated[
        Optional[Dict[str, str]],
        Field(
            description=(
                "The custom tags to associate with the volume."
                " The tags are also propagated to the underlying backend resources."
                " If there is a conflict with backend-level tags, does not override them"
            )
        ),
    ] = None

    _validate_tags = validator("tags", pre=True, allow_reuse=True)(tags_validator)

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


class VolumeInstance(CoreModel):
    name: str
    fleet_name: Optional[str] = None
    instance_num: int
    instance_id: Optional[str] = None


class VolumeAttachment(CoreModel):
    instance: VolumeInstance
    attachment_data: Optional[VolumeAttachmentData] = None


class Volume(CoreModel):
    id: uuid.UUID
    name: str
    user: str
    project_name: str
    configuration: VolumeConfiguration
    external: bool
    created_at: datetime
    last_processed_at: datetime
    status: VolumeStatus
    status_message: Optional[str] = None
    deleted: bool
    deleted_at: Optional[datetime] = None
    volume_id: Optional[str] = None  # id of the volume in the cloud
    provisioning_data: Optional[VolumeProvisioningData] = None
    cost: float = 0
    attachments: Optional[List[VolumeAttachment]] = None
    # attachment_data is deprecated in favor of attachments.
    # It's only set for volumes that were attached before attachments.
    attachment_data: Optional[VolumeAttachmentData] = None

    def get_attachment_data_for_instance(self, instance_id: str) -> Optional[VolumeAttachmentData]:
        if self.attachments is not None:
            for attachment in self.attachments:
                if attachment.instance.instance_id == instance_id:
                    return attachment.attachment_data
        # volume was attached before attachments were introduced
        return self.attachment_data


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
                " Specify volumes from different backends/regions to increase availability"
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
    optional: Annotated[
        bool,
        Field(
            description=(
                "Allow running without this volume"
                " in backends that do not support instance volumes"
            ),
        ),
    ] = False

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
