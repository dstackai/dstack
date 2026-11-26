import re
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

import gpuhunt
from gpuhunt.providers.runpod import RunpodProvider

from dstack._internal.core.backends.base.authorized_keys import build_authorized_keys
from dstack._internal.core.backends.base.backend import Compute
from dstack._internal.core.backends.base.compute import (
    ComputeWithFilteredOffersCached,
    ComputeWithResourceListingSupport,
    ComputeWithVolumeSupport,
    generate_unique_instance_name,
    generate_unique_volume_name,
    get_docker_commands,
    get_job_instance_name,
    get_job_provider_ref,
    parse_provider_ref_from_name,
)
from dstack._internal.core.backends.base.offers import OfferDiskFitter, get_catalog_offers
from dstack._internal.core.backends.runpod.api_client import RunpodApiClient, V2Pod
from dstack._internal.core.backends.runpod.models import RunpodConfig
from dstack._internal.core.consts import DSTACK_RUNNER_SSH_PORT
from dstack._internal.core.errors import BackendError, ComputeError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.backends.orphans import (
    ListedResourceGroup,
    OwnerType,
    ResourceListing,
)
from dstack._internal.core.models.common import RegistryAuth
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOfferWithAvailability,
)
from dstack._internal.core.models.placement import PlacementGroup
from dstack._internal.core.models.resources import Memory, Range
from dstack._internal.core.models.runs import Job, JobProvisioningData, Requirements, Run
from dstack._internal.core.models.volumes import (
    RunpodVolumeConfiguration,
    Volume,
    VolumeProvisioningData,
)
from dstack._internal.utils.common import get_current_datetime, get_or_error, parse_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

# Undocumented but names of len 60 work
MAX_RESOURCE_NAME_LEN = 60

CONTAINER_REGISTRY_AUTH_CLEANUP_INTERVAL = 60 * 60 * 24  # 24 hour

# GPU pods do not seem to have any limits on the container disk size.
CONFIGURABLE_DISK_SIZE = Range[Memory](min=Memory.parse("1GB"), max=None)

# The API does not expose storage prices. The docs (https://docs.runpod.io/pods/pricing) list
# $0.10/GB/month, which the console converts to an hourly price assuming 30-day months.
CONTAINER_DISK_PRICE_PER_GB_PER_HOUR = 0.10 / (30 * 24)

# gpuhunt builds CPU instance type names as
# {CPU flavor (aka type) identifier}-{vCPU count}-{memory in GB}, e.g., cpu3c-2-4
# REST API v2 accepts separate `id` and `vcpuCount` fields (memory is inferred)
CPU_INSTANCE_ID_REGEX = re.compile(r"(?P<flavor_id>.+)-(?P<vcpu>\d+)-(?P<memory>\d+)")


class RunpodCompute(
    ComputeWithFilteredOffersCached,
    ComputeWithVolumeSupport,
    ComputeWithResourceListingSupport,
    Compute,
):
    _last_cleanup_time = None

    def __init__(self, config: RunpodConfig):
        super().__init__()
        self.config = config
        self.api_client = RunpodApiClient(config.creds.api_key)
        self.catalog = gpuhunt.Catalog(balance_resources=False, auto_reload=False)
        self.catalog.add_provider(RunpodProvider(api_key=config.creds.api_key))

    def get_offers_by_requirements(
        self, requirements: Requirements, full_offers: bool, unallocated_resources: bool
    ) -> List[InstanceOfferWithAvailability]:
        # Offers depend on requirements: the catalog lists data centers with hosts that fit
        # the required vCPU and RAM and reports the minimum vCPU and RAM of such hosts
        offers = get_catalog_offers(
            backend=BackendType.RUNPOD,
            locations=self.config.regions or None,
            requirements=requirements,
            catalog=self.catalog,
            check_disk=False,
        )
        disk_fitter = OfferDiskFitter(requirements)
        offers_with_availability = []
        for offer in offers:
            # The catalog only lists data centers where the offer is available
            offer = offer.with_availability(availability=InstanceAvailability.AVAILABLE)
            fitted_offer = disk_fitter.fit(offer, _get_offer_disk_size_range(offer))
            if fitted_offer is not None:
                offers_with_availability.append(_add_container_disk_price(fitted_offer))
        return offers_with_availability

    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_name: str,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
        volumes: List[Volume],
        placement_group: Optional[PlacementGroup],
        requirements: Requirements,
        extra_authorized_keys: list[str],
    ) -> JobProvisioningData:
        instance_config = InstanceConfiguration(
            project_name=project_name,
            instance_name=get_job_instance_name(run, job),
            ssh_keys=[],
            user=run.user,
            provider_ref=get_job_provider_ref(job),
        )

        pod_name = generate_unique_instance_name(
            instance_config, max_length=MAX_RESOURCE_NAME_LEN, with_provider_ref=True
        )
        authorized_keys = build_authorized_keys(project_ssh_public_key, extra_authorized_keys)

        network_volume_id = None
        volume_mount_path = None
        if len(volumes) > 1:
            raise ComputeError("Mounting more than one network volume is not supported in runpod")
        if len(volumes) == 1:
            network_volume_id = volumes[0].volume_id
            volume_mount_path = run.run_spec.configuration.volumes[0].path

        if instance_offer.instance.resources.spot:
            raise ComputeError("Runpod spot offers are not supported")

        offer_gpu_count = len(instance_offer.instance.resources.gpus)
        offer_cpu_count = instance_offer.instance.resources.cpus
        offer_memory_gib = round(instance_offer.instance.resources.memory_mib / 1024)
        offer_disk_gib = _get_offer_container_disk_gib(instance_offer)

        gpu_type_id: Optional[str] = None
        gpu_count: Optional[int] = None
        min_cpu_count_per_gpu: Optional[int] = None
        min_memory_in_gb_per_gpu: Optional[int] = None
        cpu_type_id: Optional[str] = None
        cpu_count: Optional[int] = None
        if offer_gpu_count > 0:
            gpu_type_id = instance_offer.instance.name
            gpu_count = offer_gpu_count
            # Offer resources are the minimum host totals that fit the requirements.
            # Round down, since rounding up may exclude the hosts the offer is based on
            min_cpu_count_per_gpu = offer_cpu_count // gpu_count
            min_memory_in_gb_per_gpu = offer_memory_gib // gpu_count
        else:
            cpu_type_id = _get_cpu_type_id(instance_offer)
            cpu_count = offer_cpu_count

        container_registry_credentials_id = self._generate_container_registry_credentials_id(
            job.job_spec.registry_auth
        )

        pod = self.api_client.create_pod(
            name=pod_name,
            cloud="SECURE",
            data_center_ids=[instance_offer.region],
            gpu_type_id=gpu_type_id,
            gpu_count=gpu_count,
            min_cpu_count_per_gpu=min_cpu_count_per_gpu,
            min_memory_in_gb_per_gpu=min_memory_in_gb_per_gpu,
            cpu_type_id=cpu_type_id,
            cpu_count=cpu_count,
            container_disk_in_gb=offer_disk_gib,
            network_volume_id=network_volume_id,
            volume_mount_path=volume_mount_path,
            image_name=job.job_spec.image_name,
            container_registry_credentials_id=container_registry_credentials_id,
            entrypoint=["/bin/sh"],
            cmd=["-c", " && ".join(get_docker_commands(authorized_keys))],
            ports=[f"{DSTACK_RUNNER_SSH_PORT}/tcp"],
            env={"RUNPOD_POD_USER": "0"},
        )
        instance_id = pod["id"]

        if (
            self._last_cleanup_time is None
            or self._last_cleanup_time
            < get_current_datetime() - timedelta(seconds=CONTAINER_REGISTRY_AUTH_CLEANUP_INTERVAL)
        ):
            # The pod is already created, a failed cleanup must not fail provisioning
            try:
                self._clean_stale_container_registry_credentials()
            except Exception as e:
                logger.warning(
                    "Failed to clean up stale container registry credentials: %r",
                    e,
                    exc_info=not isinstance(e, BackendError),
                )
            self._last_cleanup_time = get_current_datetime()

        return JobProvisioningData(
            backend=instance_offer.backend,
            instance_type=instance_offer.instance,
            instance_id=instance_id,
            hostname=None,
            internal_ip=None,
            region=instance_offer.region,
            price=instance_offer.price,
            username="root",
            ssh_port=None,
            dockerized=False,
            ssh_proxy=None,
            backend_data=None,
        )

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        terminated = self.api_client.terminate_pod(instance_id)
        if not terminated:
            logger.debug("The instance %s not found. Skipping deletion.", instance_id)

    def update_provisioning_data(
        self,
        provisioning_data: JobProvisioningData,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ):
        instance_id = provisioning_data.instance_id
        pod = self.api_client.get_pod(instance_id)
        if pod is None or pod["runtime"] is None:
            return
        ports = pod["runtime"].get("ports")
        if ports is None:
            return
        for port in ports:
            if port.get("private") == DSTACK_RUNNER_SSH_PORT:
                provisioning_data.hostname = port.get("ip")
                provisioning_data.ssh_port = port.get("public")

    def list_resource_groups(self) -> ResourceListing:
        resource_groups = []
        pods = self.api_client.list_pods()
        for pod in pods:
            if pod["status"] == "TERMINATED":
                continue
            provider_ref = parse_provider_ref_from_name(pod["name"])
            if provider_ref is None:
                continue
            resource_group = ListedResourceGroup(
                backend=BackendType.RUNPOD,
                owner_type=OwnerType.INSTANCE,
                provider_ref=provider_ref,
                primary_id=pod["id"],
                region=pod["dataCenterId"],
                created_at=_parse_pod_created_at(pod),
                description=f"pod {pod['id']}",
                backend_data=None,
            )
            resource_groups.append(resource_group)
        return ResourceListing(
            resource_groups=resource_groups,
            failures=[],
        )

    def delete_resource_group(self, group: ListedResourceGroup) -> None:
        if group.primary_id is None:
            return
        self.api_client.terminate_pod(group.primary_id)

    def register_volume(self, volume: Volume) -> VolumeProvisioningData:
        assert isinstance(volume.configuration, RunpodVolumeConfiguration)
        volume_id = get_or_error(volume.configuration.volume_id)
        network_volume = self.api_client.get_network_volume(volume_id)
        if network_volume is None:
            raise ComputeError(f"Volume {volume_id} not found")
        size_gb = network_volume["size"]
        return VolumeProvisioningData(
            backend=BackendType.RUNPOD,
            volume_id=network_volume["id"],
            size_gb=size_gb,
            price=_get_volume_price(size_gb),
            attachable=False,
            detachable=False,
        )

    def create_volume(self, volume: Volume) -> VolumeProvisioningData:
        assert isinstance(volume.configuration, RunpodVolumeConfiguration)
        volume_name = generate_unique_volume_name(volume, max_length=MAX_RESOURCE_NAME_LEN)
        size_gb = volume.configuration.size_gb
        # Runpod regions must be uppercase.
        # Lowercase regions are accepted in the API but they break Runpod in several ways.
        data_center_id = volume.configuration.region.upper()
        network_volume = self.api_client.create_network_volume(
            name=volume_name,
            data_center_id=data_center_id,
            size=size_gb,
        )
        return VolumeProvisioningData(
            backend=BackendType.RUNPOD,
            volume_id=network_volume["id"],
            size_gb=size_gb,
            price=_get_volume_price(size_gb),
            attachable=False,
            detachable=False,
        )

    def delete_volume(self, volume: Volume):
        if volume.volume_id is None:
            return
        deleted = self.api_client.delete_network_volume(volume.volume_id)
        if not deleted:
            logger.debug("The volume %s not found. Skipping deletion.", volume.volume_id)

    def _generate_container_registry_credentials_id(
        self, registry_auth: Optional[RegistryAuth]
    ) -> Optional[str]:
        if registry_auth is None:
            return None
        creds = self.api_client.create_container_registry_credentials(
            name=uuid.uuid4().hex,
            username=registry_auth.username,
            password=registry_auth.password,
        )
        return creds["id"]

    def _clean_stale_container_registry_credentials(self) -> None:
        # XXX: Credentials are sorted by creation time so try to delete the oldest first.
        # When we reach credentials that is still in use, we stop.
        # > Permanently deletes a container registry credential by ID. Rejected if any pod
        # > currently uses this credential to pull its image. Templates that reference it are not
        # > part of that check — they silently lose the reference (registry becomes null) instead
        # > of blocking the delete.
        for creds in self.api_client.list_container_registry_credentials():
            try:
                self.api_client.delete_container_registry_credentials(creds["id"])
            except Exception:
                break


def _get_offer_disk_size_range(offer: InstanceOfferWithAvailability) -> Range[Memory]:
    if len(offer.instance.resources.gpus) > 0:
        return CONFIGURABLE_DISK_SIZE
    # For Runpod CPU offers, gpuhunt disk is the per-flavor max.
    return Range[Memory](
        min=Memory.parse("1GB"),
        max=Memory(offer.instance.resources.disk.size_mib / 1024),
    )


def _add_container_disk_price(
    offer: InstanceOfferWithAvailability,
) -> InstanceOfferWithAvailability:
    # Catalog prices only include compute
    disk_price = _get_offer_container_disk_gib(offer) * CONTAINER_DISK_PRICE_PER_GB_PER_HOUR
    return offer.model_copy(update={"price": offer.price + disk_price})


def _get_offer_container_disk_gib(offer: InstanceOfferWithAvailability) -> int:
    return round(offer.instance.resources.disk.size_mib / 1024)


def _get_volume_price(size: int) -> float:
    if size < 1000:
        return 0.07 * size
    return 0.05 * size


def _get_cpu_type_id(offer: InstanceOfferWithAvailability) -> str:
    match = CPU_INSTANCE_ID_REGEX.fullmatch(offer.instance.name)
    if match is None:
        raise ComputeError(f"Failed to parse CPU instance type: {offer.instance.name!r}")
    return match.group("flavor_id")


def _parse_pod_created_at(pod: V2Pod) -> Optional[datetime]:
    try:
        return parse_datetime(pod["createdAt"])
    except ValueError:
        logger.warning("Failed to parse createdAt %r of pod %s", pod["createdAt"], pod["id"])
        return None
