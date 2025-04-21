import json
import uuid
from datetime import timedelta
from typing import List, Optional

from dstack._internal.core.backends.base.backend import Compute
from dstack._internal.core.backends.base.compute import (
    ComputeWithVolumeSupport,
    generate_unique_instance_name,
    generate_unique_volume_name,
    get_docker_commands,
    get_job_instance_name,
)
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.runpod.api_client import RunpodApiClient
from dstack._internal.core.backends.runpod.models import RunpodConfig
from dstack._internal.core.consts import DSTACK_RUNNER_SSH_PORT
from dstack._internal.core.errors import (
    BackendError,
    ComputeError,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import RegistryAuth
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOfferWithAvailability,
    SSHKey,
)
from dstack._internal.core.models.runs import Job, JobProvisioningData, Requirements, Run
from dstack._internal.core.models.volumes import Volume, VolumeProvisioningData
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

# Undocumented but names of len 60 work
MAX_RESOURCE_NAME_LEN = 60

CONTAINER_REGISTRY_AUTH_CLEANUP_INTERVAL = 60 * 60 * 24  # 24 hour


class RunpodCompute(
    ComputeWithVolumeSupport,
    Compute,
):
    _last_cleanup_time = None

    def __init__(self, config: RunpodConfig):
        super().__init__()
        self.config = config
        self.api_client = RunpodApiClient(config.creds.api_key)

    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            backend=BackendType.RUNPOD,
            locations=self.config.regions or None,
            requirements=requirements,
            extra_filter=lambda o: _is_secure_cloud(o.region) or self.config.allow_community_cloud,
        )
        offers = [
            InstanceOfferWithAvailability(
                **offer.dict(), availability=InstanceAvailability.AVAILABLE
            )
            for offer in offers
        ]
        return offers

    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
        volumes: List[Volume],
    ) -> JobProvisioningData:
        instance_config = InstanceConfiguration(
            project_name=run.project_name,
            instance_name=get_job_instance_name(run, job),
            ssh_keys=[
                SSHKey(public=run.run_spec.ssh_key_pub.strip()),
                SSHKey(public=project_ssh_public_key.strip()),
            ],
            user=run.user,
        )

        pod_name = generate_unique_instance_name(instance_config, max_length=MAX_RESOURCE_NAME_LEN)
        authorized_keys = instance_config.get_public_keys()
        memory_size = round(instance_offer.instance.resources.memory_mib / 1024)
        disk_size = round(instance_offer.instance.resources.disk.size_mib / 1024)

        network_volume_id = None
        volume_mount_path = None
        if len(volumes) > 1:
            raise ComputeError("Mounting more than one network volume is not supported in runpod")
        if len(volumes) == 1:
            network_volume_id = volumes[0].volume_id
            volume_mount_path = run.run_spec.configuration.volumes[0].path

        container_registry_auth_id = self._generate_container_registry_auth_id(
            job.job_spec.registry_auth
        )
        gpu_count = len(instance_offer.instance.resources.gpus)
        bid_per_gpu = None
        if instance_offer.instance.resources.spot and gpu_count:
            bid_per_gpu = instance_offer.price / gpu_count
        if _is_secure_cloud(instance_offer.region):
            cloud_type = "SECURE"
            data_center_id = instance_offer.region
            country_code = None
        else:
            cloud_type = "COMMUNITY"
            data_center_id = None
            country_code = instance_offer.region

        resp = self.api_client.create_pod(
            name=pod_name,
            image_name=job.job_spec.image_name,
            gpu_type_id=instance_offer.instance.name,
            cloud_type=cloud_type,
            data_center_id=data_center_id,
            country_code=country_code,
            gpu_count=gpu_count,
            container_disk_in_gb=disk_size,
            min_vcpu_count=instance_offer.instance.resources.cpus,
            min_memory_in_gb=memory_size,
            support_public_ip=True,
            docker_args=_get_docker_args(authorized_keys),
            ports=f"{DSTACK_RUNNER_SSH_PORT}/tcp",
            bid_per_gpu=bid_per_gpu,
            network_volume_id=network_volume_id,
            volume_mount_path=volume_mount_path,
            env={"RUNPOD_POD_USER": "0"},
        )

        instance_id = resp["id"]

        # TODO: remove editPod once createPod supports docker's username and password
        # editPod is temporary solution to set container_registry_auth_id because createPod does not
        # support it currently. This will be removed once createPod supports container_registry_auth_id
        # or username and password
        if container_registry_auth_id is not None:
            instance_id = self.api_client.edit_pod(
                pod_id=instance_id,
                image_name=job.job_spec.image_name,
                container_disk_in_gb=disk_size,
                container_registry_auth_id=container_registry_auth_id,
            )

        if (
            self._last_cleanup_time is None
            or self._last_cleanup_time
            < get_current_datetime() - timedelta(seconds=CONTAINER_REGISTRY_AUTH_CLEANUP_INTERVAL)
        ):
            self._clean_stale_container_registry_auths()
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
    ) -> None:
        try:
            self.api_client.terminate_pod(instance_id)
        except BackendError as e:
            if e.args[0] == "Instance Not Found":
                logger.debug("The instance with name %s not found", instance_id)
                return
            raise

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
        for port in pod["runtime"]["ports"]:
            if port["privatePort"] == DSTACK_RUNNER_SSH_PORT:
                provisioning_data.hostname = port["ip"]
                provisioning_data.ssh_port = port["publicPort"]

    def register_volume(self, volume: Volume) -> VolumeProvisioningData:
        volume_data = self.api_client.get_network_volume(volume_id=volume.configuration.volume_id)
        if volume_data is None:
            raise ComputeError(f"Volume {volume.configuration.volume_id} not found")
        size_gb = volume_data["size"]
        return VolumeProvisioningData(
            backend=BackendType.RUNPOD,
            volume_id=volume_data["id"],
            size_gb=size_gb,
            price=_get_volume_price(size_gb),
            attachable=False,
            detachable=False,
        )

    def create_volume(self, volume: Volume) -> VolumeProvisioningData:
        volume_name = generate_unique_volume_name(volume, max_length=MAX_RESOURCE_NAME_LEN)
        size_gb = volume.configuration.size_gb
        volume_id = self.api_client.create_network_volume(
            name=volume_name,
            region=volume.configuration.region,
            size=size_gb,
        )
        return VolumeProvisioningData(
            backend=BackendType.RUNPOD,
            volume_id=volume_id,
            size_gb=size_gb,
            price=_get_volume_price(size_gb),
            attachable=False,
            detachable=False,
        )

    def delete_volume(self, volume: Volume):
        if volume.volume_id is not None:
            self.api_client.delete_network_volume(volume_id=volume.volume_id)

    def _generate_container_registry_auth_id(
        self, registry_auth: Optional[RegistryAuth]
    ) -> Optional[str]:
        if registry_auth is None:
            return None

        return self.api_client.add_container_registry_auth(
            uuid.uuid4().hex, registry_auth.username, registry_auth.password
        )

    def _clean_stale_container_registry_auths(self) -> None:
        container_registry_auths = self.api_client.get_container_registry_auths()

        # Container_registry_auths sorted by creation time so try to delete the oldest first
        # when we reach container_registry_auths that is still in use, we stop
        for container_registry_auth in container_registry_auths:
            try:
                self.api_client.delete_container_registry_auth(container_registry_auth["id"])
            except Exception:
                break


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


def _is_secure_cloud(region: str) -> str:
    """
    Secure cloud regions are datacenter IDs: CA-MTL-1, EU-NL-1, etc.
    Community cloud regions are country codes: CA, NL, etc.
    """
    return "-" in region
