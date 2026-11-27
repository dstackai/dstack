import re
import shlex
from typing import Optional
from uuid import UUID

import gpuhunt
from gpuhunt.providers.massedcompute import MassedComputeProvider

from dstack._internal.core.backends.base.authorized_keys import get_add_authorized_keys_script
from dstack._internal.core.backends.base.compute import (
    Compute,
    ComputeWithAllOffersCached,
    ComputeWithCreateInstanceSupport,
    ComputeWithInstanceVolumesSupport,
    ComputeWithPrivilegedSupport,
    ComputeWithResourceListingSupport,
    ComputeWithVolumeSupport,
    generate_unique_instance_name,
    get_shim_commands,
    parse_provider_ref_from_name,
)
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.massedcompute.api_client import (
    MassedComputeAPIClient,
    MassedComputeInstance,
    MassedComputeLaunchUnconfirmed,
    MassedComputeVolume,
)
from dstack._internal.core.backends.massedcompute.models import MassedComputeConfig
from dstack._internal.core.errors import (
    BackendError,
    ComputeError,
    NotYetTerminated,
    ProvisioningError,
    VolumeDeletionPending,
    VolumeProvisioningError,
    VolumeProvisioningPending,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.backends.orphans import (
    ListedResourceGroup,
    OwnerType,
    ResourceListing,
)
from dstack._internal.core.models.common import CoreModel, validate_json_extra_ignore
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOfferWithAvailability,
)
from dstack._internal.core.models.placement import PlacementGroup
from dstack._internal.core.models.runs import JobProvisioningData
from dstack._internal.core.models.volumes import Volume, VolumeProvisioningData, VolumeStatus
from dstack._internal.utils.common import get_or_error
from dstack._internal.utils.hash import slugify


class MassedComputeCompute(
    ComputeWithAllOffersCached,
    ComputeWithCreateInstanceSupport,
    ComputeWithInstanceVolumesSupport,
    ComputeWithPrivilegedSupport,
    ComputeWithResourceListingSupport,
    ComputeWithVolumeSupport,
    Compute,
):
    def __init__(self, config: MassedComputeConfig):
        super().__init__()
        self.api_client = MassedComputeAPIClient(config.creds.api_key)
        self.catalog = gpuhunt.Catalog(balance_resources=False, auto_reload=False)
        self.catalog.add_provider(MassedComputeProvider(config.creds.api_key))

    def get_all_offers_with_availability(
        self, unallocated_resources: bool
    ) -> list[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(backend=BackendType.MASSEDCOMPUTE, catalog=self.catalog)
        return [
            offer.with_availability(availability=InstanceAvailability.AVAILABLE)
            for offer in offers
        ]

    def create_instance(
        self,
        instance_offer: InstanceOfferWithAvailability,
        instance_config: InstanceConfiguration,
        placement_group: Optional[PlacementGroup],
    ) -> JobProvisioningData:
        # The image's SSH user is case-sensitive. The startup command runs as root.
        key_script = get_add_authorized_keys_script(instance_config.get_public_keys())
        install_keys = shlex.join(["sudo", "-H", "-u", "Ubuntu", "sh", "-c", key_script])
        command = " && ".join(
            [install_keys, *get_shim_commands(arch=instance_offer.instance.resources.cpu_arch)]
        )
        if not instance_config.volumes:
            name = generate_unique_instance_name(instance_config, with_provider_ref=True)
            instance_id = self.api_client.launch(name, instance_offer.instance.name, command)
            return _instance_provisioning_data(instance_offer, instance_id)

        volumes = self._get_launch_volumes(instance_config.volumes)
        # The suffix identifies VMs that orphan cleanup cannot flush. Keep the total name
        # within the same 60-character limit as an ordinary generated instance name.
        name = (
            generate_unique_instance_name(
                instance_config, max_length=60 - len(_VOLUME_VM_SUFFIX), with_provider_ref=True
            )
            + _VOLUME_VM_SUFFIX
        )
        launch = _VolumeLaunch(name=name, volume_ids={k: v.id for k, v in volumes.items()})
        try:
            instance_id = self.api_client.launch(
                name, instance_offer.instance.name, command, [str(v.id) for v in volumes.values()]
            )
        except MassedComputeLaunchUnconfirmed:
            # Returning incomplete provisioning data keeps the scheduler on this launch.
            instance_id = name
        data = _instance_provisioning_data(instance_offer, instance_id)
        data.backend_data = launch.model_dump_json()
        data.volume_mounts = {k: v.mount_path for k, v in volumes.items()}
        return data

    def _get_launch_volumes(self, volumes: list[Volume]) -> dict[UUID, MassedComputeVolume]:
        if len(volumes) > 8:
            raise ComputeError("MassedCompute accepts up to eight volumes per VM")
        available = {str(v.id): v for v in self.api_client.list_volumes()}
        selected = {}
        for volume in volumes:
            data = volume.provisioning_data
            if (
                data is None
                or not data.mount_on_instance
                or data.backend != BackendType.MASSEDCOMPUTE
            ):
                raise ComputeError(f"Invalid MassedCompute volume {volume.name}")
            # Consuming each provider UUID once also detects two registrations of the same disk.
            storage = available.pop(data.volume_id.lower(), None)
            if (
                storage is None
                or storage.status != "active"
                or not storage.can_manage
                or storage.attached_to
                or storage.hidden_attached_count
            ):
                raise ComputeError(f"MassedCompute volume {volume.name} is unavailable or in use")
            _check_volume_mount_path(storage)
            selected[volume.id] = storage
        return selected

    def update_provisioning_data(
        self,
        provisioning_data: JobProvisioningData,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ) -> None:
        launch = (
            validate_json_extra_ignore(_VolumeLaunch, provisioning_data.backend_data)
            if provisioning_data.backend_data is not None
            else None
        )
        instance = self._get_instance(provisioning_data.instance_id, launch)
        if instance is None:
            return
        if launch is not None and provisioning_data.instance_id == launch.name:
            # Save the recovered UUID even if the subsequent attachment check fails or times out.
            provisioning_data.instance_id = str(instance.get_uuid())
            return
        if instance.status.lower() == "stopped":
            raise ProvisioningError("MassedCompute instance stopped during provisioning")
        if instance.os_booted and instance.ip and instance.username:
            if launch is not None:
                expected = provisioning_data.volume_mounts or {}
                if expected.keys() != launch.volume_ids.keys():
                    raise ProvisioningError("MassedCompute volume launch metadata is incomplete")
                instance_uuid = instance.get_uuid()
                attached = {
                    v.id: v
                    for v in self.api_client.list_volumes()
                    if v.status == "active"
                    and not v.hidden_attached_count
                    and [i.uuid for i in v.attached_to] == [instance_uuid]
                }
                for registration_id, provider_id in launch.volume_ids.items():
                    volume = attached.get(provider_id)
                    if volume is None or volume.mount_path != expected[registration_id]:
                        raise ProvisioningError(
                            f"MassedCompute failed to attach volume {provider_id} to the VM"
                        )
                    _check_volume_mount_path(volume)
                provisioning_data.backend_data = None
            provisioning_data.hostname = instance.ip
            provisioning_data.username = instance.username

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ) -> None:
        launch = validate_json_extra_ignore(_VolumeLaunch, backend_data) if backend_data else None
        instance = self._get_instance(instance_id, launch)
        if instance is None:
            # A cancelled name-only launch may appear later. Its -fs suffix makes orphan
            # cleanup report the VM for manual removal without deleting its mounted volumes.
            return
        if instance.status.lower() not in {"terminating", "deleting"}:
            # An unconfirmed launch is looked up by name, but termination always takes a UUID.
            self.api_client.terminate(instance.uuid)
        raise NotYetTerminated(f"Waiting for MassedCompute instance {instance_id} to terminate")

    def _get_instance(
        self, instance_id: str, launch: Optional["_VolumeLaunch"]
    ) -> Optional[MassedComputeInstance]:
        if launch is not None and instance_id == launch.name:
            instance = self.api_client.get_instance_by_name(launch.name)
            if instance is None:
                return None
            instance_id = str(instance.get_uuid())
        instance = self.api_client.get_instance(instance_id)
        if launch is not None and instance is not None and instance.name != launch.name:
            raise ComputeError("MassedCompute returned an unexpected volume VM name")
        return instance

    def get_volume_mounts_to_sync(
        self, provisioning_data: JobProvisioningData
    ) -> Optional[list[str]]:
        instance = self.api_client.get_instance(provisioning_data.instance_id)
        if instance is None:
            return None
        if instance.status.lower() in {"terminating", "deleting"}:
            raise NotYetTerminated(
                f"Waiting for MassedCompute instance {instance.uuid} to terminate"
            )
        if instance.status.lower() == "stopped":
            raise ComputeError(
                "Cannot flush volumes on a stopped MassedCompute VM. "
                "Restart the VM to flush its volumes, or terminate it manually in MassedCompute."
            )
        return list((provisioning_data.volume_mounts or {}).values())

    def register_volume(self, volume: Volume) -> VolumeProvisioningData:
        volume_id = get_or_error(volume.configuration.external_volume_id)
        provisioned = next(
            (v for v in self.api_client.list_volumes() if str(v.id) == volume_id.lower()), None
        )
        if provisioned is None:
            raise ComputeError(f"MassedCompute volume {volume_id} not found")
        return _volume_provisioning_data(provisioned)

    def create_volume(self, volume: Volume) -> VolumeProvisioningData:
        name = _managed_volume_name(volume)
        if volume.status == VolumeStatus.SUBMITTED:
            volume_id = self.api_client.create_volume(name)
            raise VolumeProvisioningPending(f"Waiting for MassedCompute volume {name}", volume_id)

        # A restarted worker cannot know whether the first request reached the provider.
        # A deleted name is reusable, so only the worker that claimed SUBMITTED may POST.
        try:
            volumes = self.api_client.list_volumes()
        except BackendError as e:
            raise VolumeProvisioningPending(str(e), volume.volume_id) from e
        if volume.volume_id is None:
            existing = next((v for v in volumes if v.name == name), None)
        else:
            existing = next((v for v in volumes if str(v.id) == volume.volume_id), None)
        if existing is None:
            raise VolumeProvisioningPending(
                f"Waiting for MassedCompute volume {name}", volume.volume_id
            )
        if existing.name != name:
            raise VolumeProvisioningError(
                f"Unexpected name for MassedCompute volume {existing.id}", str(existing.id)
            )
        try:
            return _volume_provisioning_data(existing)
        except VolumeProvisioningPending:
            raise
        except ComputeError as e:
            raise VolumeProvisioningError(str(e), str(existing.id)) from e

    def delete_volume(self, volume: Volume) -> None:
        if volume.external:
            return
        volume_id = volume.volume_id
        if volume_id is None:
            name = _managed_volume_name(volume)
            try:
                existing = next(
                    (v for v in self.api_client.list_volumes() if v.name == name), None
                )
            except BackendError as e:
                raise VolumeDeletionPending(str(e)) from e
            if existing is None:
                raise VolumeDeletionPending(
                    f"Could not confirm creation of MassedCompute volume {name}"
                )
            # Persist the recovered UUID before a DELETE can remove the only name lookup.
            raise VolumeDeletionPending(f"Found MassedCompute volume {name}", str(existing.id))
        self.api_client.delete_volume(volume_id)

    def list_resource_groups(self) -> ResourceListing:
        groups = []
        for instance in self.api_client.list_instances():
            provider_ref = parse_provider_ref_from_name(
                instance.name.removesuffix(_VOLUME_VM_SUFFIX)
            )
            if provider_ref is None or instance.status.lower() in {"terminating", "deleting"}:
                continue
            groups.append(
                ListedResourceGroup(
                    backend=BackendType.MASSEDCOMPUTE,
                    owner_type=OwnerType.INSTANCE,
                    provider_ref=provider_ref,
                    primary_id=instance.uuid.lower(),
                    region="any",
                    created_at=instance.created,
                    description=instance.name,
                    backend_data=(
                        _VOLUME_VM_SUFFIX if instance.name.endswith(_VOLUME_VM_SUFFIX) else None
                    ),
                )
            )
        return ResourceListing(resource_groups=groups)

    def delete_resource_group(self, group: ListedResourceGroup) -> None:
        if group.primary_id is None:
            return
        if group.backend_data == _VOLUME_VM_SUFFIX:
            raise ComputeError(
                "MassedCompute volume VM retained: orphan cleanup cannot flush its mounted volumes"
            )
        self.terminate_instance(group.primary_id, "any")


class _VolumeLaunch(CoreModel):
    """Private provider identities retained until the VM confirms its launch attachments."""

    name: str
    volume_ids: dict[UUID, UUID]
    """dstack volume registration ID to MassedCompute storage UUID."""


_VOLUME_VM_SUFFIX = "-fs"


def _instance_provisioning_data(
    offer: InstanceOfferWithAvailability, instance_id: str
) -> JobProvisioningData:
    return JobProvisioningData(
        backend=offer.backend,
        instance_type=offer.instance,
        instance_id=instance_id,
        hostname=None,
        internal_ip=None,
        region=offer.region,
        price=offer.price,
        username="Ubuntu",
        ssh_port=22,
        dockerized=True,
        ssh_proxy=None,
        backend_data=None,
    )


def _managed_volume_name(volume: Volume) -> str:
    # Provider names are unique per account and limited to 22 characters.
    return slugify("dstack", str(volume.id), hash_size=15)


_VOLUME_MOUNT_PATH = re.compile(r"/persistent/[a-z0-9](?:[a-z0-9-]{0,20}[a-z0-9])?")


def _volume_provisioning_data(volume: MassedComputeVolume) -> VolumeProvisioningData:
    if volume.status == "creating":
        raise VolumeProvisioningPending(
            f"MassedCompute volume {volume.id} is creating", str(volume.id)
        )
    if volume.status != "active":
        raise ComputeError(f"MassedCompute volume {volume.id} is {volume.status}")
    _check_volume_mount_path(volume)
    return VolumeProvisioningData(
        backend=BackendType.MASSEDCOMPUTE,
        volume_id=str(volume.id),
        size_gb=None,
        attachable=False,
        detachable=False,
        mount_on_instance=True,
    )


def _check_volume_mount_path(volume: MassedComputeVolume) -> None:
    if (
        not _VOLUME_MOUNT_PATH.fullmatch(volume.mount_path)
        or volume.mount_path != f"/persistent/{volume.name}"
    ):
        raise ComputeError("Invalid MassedCompute volume mount path")
