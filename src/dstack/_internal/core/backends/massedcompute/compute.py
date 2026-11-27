import re
import shlex
import time
from typing import Optional

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
from dstack._internal.core.models.volumes import Volume, VolumeProvisioningData
from dstack._internal.utils.common import get_or_error


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
        name = generate_unique_instance_name(instance_config, with_provider_ref=True)
        # The image's SSH user is case-sensitive. The startup command runs as root.
        key_script = get_add_authorized_keys_script(instance_config.get_public_keys())
        install_keys = shlex.join(["sudo", "-H", "-u", "Ubuntu", "sh", "-c", key_script])
        command = " && ".join(
            [install_keys, *get_shim_commands(arch=instance_offer.instance.resources.cpu_arch)]
        )
        volume_mounts = self._get_volume_mounts(instance_config.volumes or [])
        instance_id = self.api_client.launch(
            name, instance_offer.instance.name, command, list(volume_mounts)
        )
        return JobProvisioningData(
            backend=instance_offer.backend,
            instance_type=instance_offer.instance,
            instance_id=instance_id or name,
            hostname=None,
            internal_ip=None,
            region=instance_offer.region,
            price=instance_offer.price,
            username="Ubuntu",
            ssh_port=22,
            dockerized=True,
            ssh_proxy=None,
            volume_mounts=volume_mounts or None,
            backend_data=_MassedComputeLaunch(name=name).model_dump_json(),
        )

    def update_provisioning_data(
        self,
        provisioning_data: JobProvisioningData,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ) -> None:
        instance = self._get_instance(
            provisioning_data.instance_id, provisioning_data.backend_data
        )
        if instance is None:
            return
        if provisioning_data.backend_data is not None:
            provisioning_data.instance_id = str(instance.uuid)
            provisioning_data.backend_data = None
            if provisioning_data.volume_mounts:
                # Persist the confirmed UUID before a guest mount check can delay admission.
                return
        if instance.status.lower() == "stopped":
            raise ProvisioningError("MassedCompute instance stopped during provisioning")
        if instance.os_booted and instance.ip and instance.username:
            if provisioning_data.volume_mounts:
                attached = {
                    str(v.id): v.mount_path
                    for v in self.api_client.list_volumes()
                    if not v.hidden_attached_count
                    and [i.uuid for i in v.attached_to] == [instance.uuid]
                }
                for volume_id, path in provisioning_data.volume_mounts.items():
                    if attached.get(volume_id) != path:
                        raise ProvisioningError(
                            f"MassedCompute failed to attach volume {volume_id} to the VM"
                        )
            provisioning_data.hostname = instance.ip
            provisioning_data.username = instance.username

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ) -> None:
        instance = self._get_instance(instance_id, backend_data)
        if backend_data is not None:
            if instance is None:
                # The API has no launch status or visibility deadline. If this VM never
                # appears, termination cannot release its exclusive volumes automatically.
                raise ComputeError(f"MassedCompute has not returned VM details for {instance_id}")
            # Record that the VM was visible by UUID before deleting it.
            raise NotYetTerminated(
                f"Found MassedCompute instance {instance.uuid} for {instance_id}",
                instance_id=str(instance.uuid),
            )
        if instance is None:
            return
        if instance.status.lower() not in {"terminating", "deleting"}:
            self.api_client.terminate(instance_id)
        raise NotYetTerminated(f"Waiting for MassedCompute instance {instance_id} to terminate")

    def _get_instance(
        self, instance_id: str, backend_data: Optional[str]
    ) -> Optional[MassedComputeInstance]:
        """Read VM details by UUID, recovering a lost launch reply by its exact name."""
        if backend_data is not None:
            launch = validate_json_extra_ignore(_MassedComputeLaunch, backend_data)
            if launch.name == instance_id:
                instance = self.api_client.get_instance_by_name(launch.name)
                if instance is None:
                    return None
                instance_id = str(instance.uuid)
        return self.api_client.get_instance(instance_id)

    def get_volume_mounts_to_sync(self, provisioning_data: JobProvisioningData) -> list[str]:
        instance = self.api_client.get_instance(provisioning_data.instance_id)
        if instance is None or instance.status.lower() in {"stopped", "terminating", "deleting"}:
            return []
        return super().get_volume_mounts_to_sync(provisioning_data)

    def register_volume(self, volume: Volume) -> VolumeProvisioningData:
        return self._wait_for_volume(get_or_error(volume.configuration.external_volume_id))

    def create_volume(self, volume: Volume) -> VolumeProvisioningData:
        # Stable across retries, including a server restart after a successful create.
        name = f"dstack-{volume.id.hex[:15]}"
        existing = next((v for v in self.api_client.list_volumes() if v.name == name), None)
        if existing is None:
            try:
                volume_id = self.api_client.create_volume(name)
            except ComputeError as e:
                existing = next(
                    (v for v in self.api_client.list_volumes() if v.name == name), None
                )
                if existing is None:
                    raise ComputeError(f"Could not confirm creation of volume {name}: {e}") from e
                volume_id = str(existing.id)
        else:
            volume_id = str(existing.id)
        try:
            return self._wait_for_volume(volume_id)
        except BackendError as e:
            try:
                self.api_client.delete_volume(volume_id)
            except VolumeDeletionPending as cleanup_error:
                raise VolumeProvisioningError(
                    f"{e}. Volume {volume_id} still needs deletion: {cleanup_error}", volume_id
                ) from e
            raise

    def _get_volume_mounts(self, volumes: list[Volume]) -> dict[str, str]:
        """Check launch-time ownership and return the host mount for each requested volume."""
        if not volumes:
            return {}
        if len(volumes) > 8:
            raise ComputeError("MassedCompute accepts up to eight volumes per VM")
        available = {str(v.id): v for v in self.api_client.list_volumes()}
        mounts = {}
        for volume in volumes:
            data = volume.provisioning_data
            if data is None or data.mount_path is None:
                raise ComputeError(f"Missing mount path for MassedCompute volume {volume.name}")
            provisioned = available.get(data.volume_id)
            if (
                provisioned is None
                or provisioned.status != "active"
                or not provisioned.can_manage
                or provisioned.attached_to
                or provisioned.hidden_attached_count
                or provisioned.mount_path != data.mount_path
            ):
                raise ComputeError(f"MassedCompute volume {volume.name} is unavailable or in use")
            mounts[data.volume_id] = data.mount_path
        return mounts

    def _wait_for_volume(self, volume_id: str) -> VolumeProvisioningData:
        deadline = time.monotonic() + 60
        while True:
            volume = next(
                (v for v in self.api_client.list_volumes() if str(v.id) == volume_id), None
            )
            if volume is None:
                raise ComputeError(f"MassedCompute volume {volume_id} not found")
            if volume.status == "active":
                return _volume_provisioning_data(volume)
            if volume.status != "creating" or time.monotonic() >= deadline:
                raise ComputeError(f"MassedCompute volume {volume_id} is {volume.status}")
            time.sleep(2)

    def delete_volume(self, volume: Volume) -> None:
        self.api_client.delete_volume(get_or_error(volume.volume_id))

    def list_resource_groups(self) -> ResourceListing:
        groups = []
        for instance in self.api_client.list_instances():
            provider_ref = parse_provider_ref_from_name(instance.name)
            if provider_ref is None or instance.status.lower() in {"terminating", "deleting"}:
                continue
            groups.append(
                ListedResourceGroup(
                    backend=BackendType.MASSEDCOMPUTE,
                    owner_type=OwnerType.INSTANCE,
                    provider_ref=provider_ref,
                    primary_id=str(instance.uuid),
                    primary_name=instance.name,
                    region="any",
                    created_at=instance.created,
                    description=instance.name,
                    backend_data=None,
                )
            )
        return ResourceListing(resource_groups=groups)

    def delete_resource_group(self, group: ListedResourceGroup) -> None:
        if group.primary_id is not None:
            self.terminate_instance(group.primary_id, "any")


class _MassedComputeLaunch(CoreModel):
    """Kept until the new VM is visible on the provider's UUID detail endpoint."""

    name: str


def _volume_provisioning_data(volume: MassedComputeVolume) -> VolumeProvisioningData:
    if (
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,20}[a-z0-9])?", volume.name)
        or volume.mount_path != f"/persistent/{volume.name}"
    ):
        raise ComputeError("Invalid MassedCompute volume mount path")
    return VolumeProvisioningData(
        backend=BackendType.MASSEDCOMPUTE,
        volume_id=str(volume.id),
        size_gb=None,
        attachable=False,
        detachable=False,
        exclusive_at_launch=True,
        mount_path=volume.mount_path,
    )
