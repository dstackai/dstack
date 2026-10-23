import json
import re
import uuid
from datetime import datetime, timedelta
from typing import Callable, List, Optional

from dstack._internal.core.backends.base.authorized_keys import build_authorized_keys
from dstack._internal.core.backends.base.backend import Compute
from dstack._internal.core.backends.base.compute import (
    ComputeWithAllOffersCached,
    ComputeWithGroupProvisioningSupport,
    ComputeWithMultinodeSupport,
    ComputeWithResourceListingSupport,
    ComputeWithVolumeSupport,
    generate_unique_instance_name,
    generate_unique_volume_name,
    get_docker_commands,
    get_job_instance_name,
    get_job_provider_ref,
    parse_provider_ref_from_name,
)
from dstack._internal.core.backends.base.models import JobConfiguration
from dstack._internal.core.backends.base.offers import get_catalog_offers
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
from dstack._internal.core.models.common import CoreModel, RegistryAuth, validate_extra_ignore
from dstack._internal.core.models.compute_groups import ComputeGroup, ComputeGroupProvisioningData
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

# Runpod does not seem to have any limits on the disk size.
CONFIGURABLE_DISK_SIZE = Range[Memory](min=Memory.parse("1GB"), max=None)

# gpuhunt, as of 0.1.30, builds CPU instance type names as
# {CPU flavor (aka type) identifier}-{vCPU count}-{memory in GB}, e.g., cpu3c-2-4
# The deprecated GraphQL API (used by old dstack servers) accepts the whole string as
# `instanceId` field; REST API v2, which we currently use, accepts separate `id` and `vcpuCount`
# fields (memory is inferred)
CPU_INSTANCE_ID_REGEX = re.compile(r"(?P<flavor_id>.+)-(?P<vcpu>\d+)-(?P<memory>\d+)")


class RunpodOfferBackendData(CoreModel):
    pod_counts: Optional[list[int]] = None


class RunpodCompute(
    ComputeWithAllOffersCached,
    ComputeWithVolumeSupport,
    ComputeWithMultinodeSupport,
    ComputeWithGroupProvisioningSupport,
    ComputeWithResourceListingSupport,
    Compute,
):
    _last_cleanup_time = None

    def __init__(self, config: RunpodConfig):
        super().__init__()
        self.config = config
        self.api_client = RunpodApiClient(config.creds.api_key)

    def get_all_offers_with_availability(
        self, unallocated_resources: bool
    ) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            backend=BackendType.RUNPOD,
            locations=self.config.regions or None,
            requirements=None,
            extra_filter=lambda o: _is_secure_cloud(o.region) or self.config.allow_community_cloud,
        )
        offers = [
            offer.with_availability(availability=InstanceAvailability.AVAILABLE)
            for offer in offers
        ]
        return offers

    def get_offer_disk_size_range(
        self, offer: InstanceOfferWithAvailability
    ) -> Optional[Range[Memory]]:
        if len(offer.instance.resources.gpus) > 0:
            return CONFIGURABLE_DISK_SIZE
        # For Runpod CPU offers, gpuhunt disk is the per-flavor max.
        return Range[Memory](
            min=Memory.parse("1GB"),
            max=Memory(offer.instance.resources.disk.size_mib / 1024),
        )

    def get_offers_post_filter(
        self, requirements: Requirements
    ) -> Optional[Callable[[InstanceOfferWithAvailability], bool]]:
        def offers_post_filter(offer: InstanceOfferWithAvailability) -> bool:
            pod_counts = _get_offer_pod_counts(offer)
            is_cluster_offer = len(pod_counts) > 0 and any(pc != 1 for pc in pod_counts)
            if requirements.multinode:
                return is_cluster_offer
            return not is_cluster_offer

        return offers_post_filter

    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
        volumes: List[Volume],
        placement_group: Optional[PlacementGroup],
        requirements: Requirements,
        extra_authorized_keys: list[str],
    ) -> JobProvisioningData:
        instance_config = InstanceConfiguration(
            project_name=run.project_name,
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
        offer_disk_gib = round(instance_offer.instance.resources.disk.size_mib / 1024)

        is_gpu_offer = offer_gpu_count > 0
        is_secure_cloud = _is_secure_cloud(instance_offer.region)
        if not is_gpu_offer and not is_secure_cloud:
            raise ComputeError("Runpod CPU offers are only supported in secure cloud regions")

        gpu_type_id: Optional[str] = None
        gpu_count: Optional[int] = None
        min_cpu_count_per_gpu: Optional[int] = None
        min_memory_in_gb_per_gpu: Optional[int] = None
        cpu_type_id: Optional[str] = None
        cpu_count: Optional[int] = None
        if is_gpu_offer:
            gpu_type_id = instance_offer.instance.name
            gpu_count = offer_gpu_count
            # Offer resources are host totals. Round down, since these are lower bounds, and
            # rounding up may exclude the host the offer is based on
            min_cpu_count_per_gpu = offer_cpu_count // gpu_count
            min_memory_in_gb_per_gpu = offer_memory_gib // gpu_count
        else:
            cpu_type_id = _get_cpu_type_id(instance_offer)
            cpu_count = offer_cpu_count

        container_registry_credentials_id = self._generate_container_registry_credentials_id(
            job.job_spec.registry_auth
        )

        if is_secure_cloud:
            # API v2 is used by default; its unified method supports both CPU and GPU pods
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
        else:
            # Deprecated GraphQL API is used for Community Cloud, as API v2 does not support
            # country codes
            assert gpu_type_id is not None
            assert gpu_count is not None
            resp = self.api_client.create_gpu_pod_graphql(
                name=pod_name,
                cloud_type="COMMUNITY",
                data_center_id=None,
                country_code=instance_offer.region,
                bid_per_gpu=None,
                support_public_ip=True,
                gpu_type_id=gpu_type_id,
                gpu_count=gpu_count,
                min_vcpu_count=offer_cpu_count,
                min_memory_in_gb=offer_memory_gib,
                container_disk_in_gb=offer_disk_gib,
                network_volume_id=network_volume_id,
                volume_mount_path=volume_mount_path,
                image_name=job.job_spec.image_name,
                container_registry_auth_id=container_registry_credentials_id,
                docker_args=_get_docker_args(authorized_keys),
                ports=f"{DSTACK_RUNNER_SSH_PORT}/tcp",
                env={"RUNPOD_POD_USER": "0"},
            )
            instance_id = resp["id"]

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

    def run_jobs(
        self,
        run: Run,
        job_configurations: List[JobConfiguration],
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
        placement_group: Optional[PlacementGroup],
        requirements: Requirements,
        extra_authorized_keys: list[str],
    ) -> ComputeGroupProvisioningData:
        master_job_configuration = job_configurations[0]
        master_job = master_job_configuration.job
        if master_job.job_spec.registry_auth is not None:
            raise ComputeError("Runpod clusters with private registries are not supported")
        master_job_volumes = master_job_configuration.volumes
        all_volumes_names = set(v.name for jc in job_configurations for v in jc.volumes)
        instance_config = InstanceConfiguration(
            project_name=run.project_name,
            instance_name=get_job_instance_name(run, master_job),
            ssh_keys=[],
            user=run.user,
        )

        cluster_name = generate_unique_instance_name(
            instance_config, max_length=MAX_RESOURCE_NAME_LEN
        )
        authorized_keys = build_authorized_keys(project_ssh_public_key, extra_authorized_keys)
        disk_size = round(instance_offer.instance.resources.disk.size_mib / 1024)

        network_volume_id = None
        volume_mount_path = None
        if len(master_job_volumes) > 1:
            raise ComputeError("Mounting more than one network volume is not supported in runpod")
        if len(all_volumes_names) > 1:
            raise ComputeError(
                "Mounting different volumes to different jobs is not supported in runpod"
            )
        if len(master_job_volumes) == 1:
            network_volume_id = master_job_volumes[0].volume_id
            volume_mount_path = run.run_spec.configuration.volumes[0].path

        offer_pod_counts = _get_offer_pod_counts(instance_offer)
        pod_count = len(job_configurations)
        gpu_count = len(instance_offer.instance.resources.gpus)
        data_center_id = instance_offer.region

        if pod_count not in offer_pod_counts:
            raise ComputeError(
                f"Failed to provision {pod_count} pods. Available pod counts: {offer_pod_counts}"
            )

        cluster = self.api_client.create_cluster(
            name=cluster_name,
            cluster_type="TRAINING",
            gpu_type_id=instance_offer.instance.name,
            gpu_count_per_pod=gpu_count,
            pod_count=pod_count,
            data_center_ids=[data_center_id],
            container_disk_in_gb=disk_size,
            network_volume_id=network_volume_id,
            volume_mount_path=volume_mount_path,
            image_name=master_job.job_spec.image_name,
            entrypoint=["/bin/sh"],
            cmd=["-c", " && ".join(get_docker_commands(authorized_keys))],
            ports=[f"{DSTACK_RUNNER_SSH_PORT}/tcp"],
            env={"RUNPOD_POD_USER": "0"},
        )
        try:
            pods = self.api_client.list_cluster_pods(cluster["id"])
            if len(pods) != pod_count:
                raise ComputeError(
                    f"Expected {pod_count} pods in cluster {cluster['id']}, got {len(pods)}"
                )
        except Exception:
            # dstack does not track the cluster until run_jobs() returns
            self._delete_cluster_after_failed_provisioning(cluster["id"])
            raise

        jpds = [
            JobProvisioningData(
                backend=instance_offer.backend,
                instance_type=instance_offer.instance,
                instance_id=pod["id"],
                hostname=None,
                # May not be assigned yet, see update_provisioning_data()
                internal_ip=_get_pod_cluster_ip(pod),
                region=instance_offer.region,
                price=instance_offer.price,
                username="root",
                dockerized=False,
            )
            for pod in pods
        ]
        return ComputeGroupProvisioningData(
            compute_group_id=cluster["id"],
            compute_group_name=cluster["name"],
            backend=BackendType.RUNPOD,
            region=instance_offer.region,
            job_provisioning_datas=jpds,
        )

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        terminated = self.api_client.terminate_pod(instance_id)
        if not terminated:
            logger.debug("The instance %s not found. Skipping deletion.", instance_id)

    def terminate_compute_group(self, compute_group: ComputeGroup):
        cluster_id = compute_group.provisioning_data.compute_group_id
        deleted = self.api_client.delete_cluster(cluster_id)
        if not deleted:
            logger.debug("The cluster %s not found. Skipping deletion.", cluster_id)

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
        if "cluster" in pod:
            # The job copies the instance's provisioning data only until the hostname is set,
            # so the internal IP must be set no later than the hostname
            internal_ip = _get_pod_cluster_ip(pod)
            if internal_ip is None:
                return
            provisioning_data.internal_ip = internal_ip
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
        self.terminate_instance(group.primary_id, group.region or "")

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

    def _delete_cluster_after_failed_provisioning(self, cluster_id: str) -> None:
        try:
            self.api_client.delete_cluster(cluster_id)
        except Exception as e:
            logger.error(
                "Failed to delete cluster %s after failed provisioning."
                " Please delete it manually to avoid unexpected charges. Error: %r",
                cluster_id,
                e,
                exc_info=not isinstance(e, BackendError),
            )


def _get_docker_args(authorized_keys: List[str]) -> str:
    commands = get_docker_commands(authorized_keys)
    command = " && ".join(commands)
    docker_args = {"cmd": [command], "entrypoint": ["/bin/sh", "-c"]}
    docker_args_escaped = json.dumps(json.dumps(docker_args)).strip('"')
    return docker_args_escaped


def _get_volume_price(size: int) -> float:
    if size < 1000:
        return 0.07 * size
    return 0.05 * size


def _is_secure_cloud(region: str) -> bool:
    """
    Secure cloud regions are datacenter IDs: CA-MTL-1, EU-NL-1, etc.
    Community cloud regions are country codes: CA, NL, etc.
    """
    return "-" in region


def _get_offer_pod_counts(offer: InstanceOfferWithAvailability) -> list[int]:
    backend_data = validate_extra_ignore(RunpodOfferBackendData, offer.backend_data)
    pod_counts = backend_data.pod_counts or []
    return pod_counts


def _get_cpu_type_id(offer: InstanceOfferWithAvailability) -> str:
    match = CPU_INSTANCE_ID_REGEX.fullmatch(offer.instance.name)
    if match is None:
        raise ComputeError(f"Failed to parse CPU instance type: {offer.instance.name!r}")
    return match.group("flavor_id")


def _get_pod_cluster_ip(pod: V2Pod) -> Optional[str]:
    cluster = pod.get("cluster")
    if cluster is None:
        return None
    return cluster.get("ip")


def _parse_pod_created_at(pod: V2Pod) -> Optional[datetime]:
    try:
        return parse_datetime(pod["createdAt"])
    except ValueError:
        logger.warning("Failed to parse createdAt %r of pod %s", pod["createdAt"], pod["id"])
        return None
