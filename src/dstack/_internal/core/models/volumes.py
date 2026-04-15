import uuid
from datetime import datetime
from enum import Enum
from pathlib import PurePosixPath
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

from pydantic import Field, ValidationError, validator
from typing_extensions import Annotated, Self

from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.profiles import parse_idle_duration
from dstack._internal.core.models.resources import Memory
from dstack._internal.utils.common import get_or_error
from dstack._internal.utils.tags import tags_validator


class VolumeStatus(str, Enum):
    SUBMITTED = "submitted"
    PROVISIONING = "provisioning"
    """`PROVISIONING` is currently not used because on all backends supporting volumes,
    volumes become `ACTIVE` almost immediately after provisioning.
    """
    ACTIVE = "active"
    FAILED = "failed"

    def is_active(self) -> bool:
        return self not in self.finished_statuses()

    @classmethod
    def finished_statuses(cls) -> List["VolumeStatus"]:
        return [cls.FAILED]


class BaseVolumeConfiguration(CoreModel):
    type: Literal["volume"] = "volume"
    backend: Any
    """`backend` is used as a tagged union discriminator. Subclasses must override its type
    with `Literal[BackendType.<BACKEND>]` annotation. Annotated as `Any` since `BackendType`
    triggers type checker error:
    > Variable is mutable so its type is invariant
    """
    name: Annotated[Optional[str], Field(description="The volume name")] = None
    size: Annotated[
        Optional[Memory],
        Field(description="The volume size. Must be specified when creating new volumes"),
    ] = None
    auto_cleanup_duration: Annotated[
        Optional[Union[str, int]],
        Field(
            description=(
                "Time to wait after volume is no longer used by any job before deleting it. "
                "Defaults to keep the volume indefinitely. "
                "Use the value `off` or `-1` to disable auto-cleanup"
            )
        ),
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
    _validate_auto_cleanup_duration = validator(
        "auto_cleanup_duration", pre=True, allow_reuse=True
    )(parse_idle_duration)

    @property
    def external_volume_id(self) -> Optional[str]:
        """
        Returns the value of a configuration field denoting a user-provided volume identifier
        when an existing volume is registered rather than a new one being created.
        """
        return None

    @property
    def is_external(self) -> bool:
        return self.external_volume_id is not None

    @property
    def size_gb(self) -> int:
        return int(get_or_error(self.size))


class VolumeConfigurationWithRegion(BaseVolumeConfiguration):
    region: Annotated[str, Field(description="The volume region")]


class VolumeConfigurationWithAvailibilityZone(VolumeConfigurationWithRegion):
    availability_zone: Annotated[
        Optional[str], Field(description="The volume availability zone")
    ] = None


class VolumeConfigurationWithVolumeID(BaseVolumeConfiguration):
    volume_id: Annotated[
        Optional[str],
        Field(description="The volume ID. Must be specified when registering external volumes"),
    ] = None

    @property
    def external_volume_id(self) -> Optional[str]:
        return self.volume_id


class AWSVolumeConfiguration(
    VolumeConfigurationWithAvailibilityZone, VolumeConfigurationWithVolumeID
):
    backend: Annotated[Literal[BackendType.AWS], Field(description="The volume backend")] = (
        BackendType.AWS
    )


class GCPVolumeConfiguration(
    VolumeConfigurationWithAvailibilityZone, VolumeConfigurationWithVolumeID
):
    backend: Annotated[Literal[BackendType.GCP], Field(description="The volume backend")] = (
        BackendType.GCP
    )


class RunpodVolumeConfiguration(VolumeConfigurationWithRegion, VolumeConfigurationWithVolumeID):
    backend: Annotated[Literal[BackendType.RUNPOD], Field(description="The volume backend")] = (
        BackendType.RUNPOD
    )
    availability_zone: Annotated[Optional[str], Field(exclude=True)] = None
    """Runpod doesn't have AZs but we accept this field for compatibility with older clients."""


class KubernetesVolumeConfiguration(BaseVolumeConfiguration):
    backend: Annotated[
        Literal[BackendType.KUBERNETES], Field(description="The volume backend")
    ] = BackendType.KUBERNETES
    size: Annotated[
        Optional[Memory],
        Field(
            description=(
                "The requested volume size. Must be specified when creating new PVCs."
                " Ignored if `claim_name` is set"
            )
        ),
    ] = None
    """`size` is overridden to provide Kubernetes-specific description.
    The signature is the same as in the base class."""
    claim_name: Annotated[
        Optional[str],
        Field(
            description=(
                "The `PersistentVolumeClaim` name. Must be specified when registering"
                " the existing PVC instead of creating a new one"
            )
        ),
    ] = None
    storage_class_name: Annotated[
        Optional[str], Field(description="The `StorageClass` name. Ignored if `claim_name` is set")
    ] = None
    access_modes: Annotated[
        list[str],
        Field(description="A list of accepted access modes. Ignored if `claim_name` is set"),
    ] = ["ReadWriteOnce"]

    @property
    def external_volume_id(self) -> Optional[str]:
        return self.claim_name


AnyVolumeConfiguration = Union[
    AWSVolumeConfiguration,
    GCPVolumeConfiguration,
    RunpodVolumeConfiguration,
    KubernetesVolumeConfiguration,
]


class VolumeConfiguration(CoreModel):
    __root__: Annotated[AnyVolumeConfiguration, Field(discriminator="backend")]


def parse_volume_configuration(data: dict) -> AnyVolumeConfiguration:
    try:
        return VolumeConfiguration.parse_obj(data).__root__
    except ValidationError as e:
        raise ConfigurationError(e)


class VolumeSpec(CoreModel):
    configuration: Annotated[AnyVolumeConfiguration, Field(discriminator="backend")]
    configuration_path: Optional[str] = None


class VolumeProvisioningData(CoreModel):
    backend: Optional[BackendType] = None
    volume_id: str
    size_gb: int
    availability_zone: Optional[str] = None
    price: Optional[float] = None
    """`price` stores the monthly price."""
    attachable: bool = True
    """`attachable` shows whether the volume should be attached and detached manually."""
    detachable: bool = True
    backend_data: Optional[str] = None
    """`backend_data` stores backend-specific data in JSON."""


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
    configuration: Annotated[AnyVolumeConfiguration, Field(discriminator="backend")]
    external: bool
    created_at: datetime
    last_processed_at: datetime
    status: VolumeStatus
    status_message: Optional[str] = None
    deleted: bool
    deleted_at: Optional[datetime] = None
    volume_id: Optional[str] = None
    """`volume_id` is the volume identifier in the cloud provider."""
    provisioning_data: Optional[VolumeProvisioningData] = None
    cost: float = 0
    attachments: Optional[List[VolumeAttachment]] = None
    attachment_data: Optional[VolumeAttachmentData] = None
    """`attachment_data` is deprecated in favor of `attachments`.
    It is only set for volumes that were attached before attachments were introduced.
    """

    def get_attachment_data_for_instance(self, instance_id: str) -> Optional[VolumeAttachmentData]:
        if self.attachments is not None:
            for attachment in self.attachments:
                if attachment.instance.instance_id == instance_id:
                    return attachment.attachment_data
        # volume was attached before attachments were introduced
        return self.attachment_data

    def get_backend(self) -> BackendType:
        return self.configuration.backend

    def get_region(self) -> str:
        """
        Returns the volume region or an empty string if the volume (that is, its backend)
        has no such thing as a "region".
        """
        if isinstance(self.configuration, VolumeConfigurationWithRegion):
            return self.configuration.region
        return ""

    def get_availability_zone(self) -> Optional[str]:
        """
        Returns the volume availability zone or `None` if:
        * the volume (that is, its backend) has no such thing as an "availability zone"
        * `VolumeProvisioningData` is not set for some reason
        """
        if self.provisioning_data is None:
            return None
        return self.provisioning_data.availability_zone


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
