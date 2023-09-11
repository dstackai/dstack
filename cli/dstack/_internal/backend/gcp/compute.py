import math
import re
import time
from typing import Dict, List, Optional

import google.api_core.exceptions
from google.cloud import compute_v1
from google.oauth2 import service_account

import dstack._internal.backend.gcp.gateway as gateway
from dstack import version
from dstack._internal.backend.base.compute import (
    WS_PORT,
    Compute,
    InstanceNotFoundError,
    NoCapacityError,
    choose_instance_type,
    get_dstack_runner,
)
from dstack._internal.backend.base.config import BACKEND_CONFIG_FILENAME, RUNNER_CONFIG_FILENAME
from dstack._internal.backend.base.runners import serialize_runner_yaml
from dstack._internal.backend.gcp import utils as gcp_utils
from dstack._internal.backend.gcp.config import GCPConfig
from dstack._internal.core.error import BackendValueError
from dstack._internal.core.gateway import GatewayHead
from dstack._internal.core.instance import (
    InstanceAvailability,
    InstanceOffer,
    InstancePricing,
    InstanceType,
    LaunchedInstanceInfo,
)
from dstack._internal.core.job import Job, Requirements
from dstack._internal.core.request import RequestHead, RequestStatus
from dstack._internal.core.runners import Gpu, Resources, Runner
from dstack._internal.hub.utils.catalog import read_catalog_csv
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

DSTACK_INSTANCE_TAG = "dstack-runner-instance"


_supported_accelerators = [
    {"accelerator_name": "nvidia-a100-80gb", "gpu_name": "A100", "memory_mb": 1024 * 80},
    {"accelerator_name": "nvidia-tesla-a100", "gpu_name": "A100", "memory_mb": 1024 * 40},
    {"accelerator_name": "nvidia-l4", "gpu_name": "L4", "memory_mb": 1024 * 24},
    # Limits from https://cloud.google.com/compute/docs/gpus
    {
        "accelerator_name": "nvidia-tesla-t4",
        "gpu_name": "T4",
        "memory_mb": 1024 * 16,
        "max_vcpu": {1: 48, 2: 48, 4: 96},
        "max_ram_mb": {1: 312 * 1024, 2: 312 * 1024, 4: 624 * 1024},
    },
    {
        "accelerator_name": "nvidia-tesla-v100",
        "gpu_name": "V100",
        "memory_mb": 1024 * 16,
        "max_vcpu": {1: 12, 2: 24, 4: 48, 8: 96},
        "max_ram_mb": {1: 78 * 1024, 2: 156 * 1024, 4: 312 * 1024, 8: 624 * 1024},
    },
    {
        "accelerator_name": "nvidia-tesla-p100",
        "gpu_name": "P100",
        "memory_mb": 1024 * 16,
        "max_vcpu": {1: 16, 2: 32, 4: 64},  # 4: 96
        "max_ram_mb": {1: 104 * 1024, 2: 208 * 1024, 4: 208 * 1024},  # 4: 624
    },
]


class GCPCompute(Compute):
    def __init__(
        self,
        gcp_config: GCPConfig,
        credentials: Optional[service_account.Credentials],
    ):
        self.gcp_config = gcp_config
        self.credentials = credentials
        self.instances_client = compute_v1.InstancesClient(credentials=self.credentials)
        self.images_client = compute_v1.ImagesClient(credentials=self.credentials)
        self.firewalls_client = compute_v1.FirewallsClient(credentials=self.credentials)
        self.machine_types_client = compute_v1.MachineTypesClient(credentials=self.credentials)
        self.accelerator_types_client = compute_v1.AcceleratorTypesClient(
            credentials=self.credentials
        )
        self.zone_operations_client = compute_v1.ZoneOperationsClient(credentials=self.credentials)
        self.regions_client = compute_v1.RegionsClient(credentials=self.credentials)

    def get_request_head(self, job: Job, request_id: Optional[str]) -> RequestHead:
        if request_id is None:
            return RequestHead(
                job_id=job.job_id,
                status=RequestStatus.TERMINATED,
                message="request_id is not specified",
            )
        instance_status = _get_instance_status(
            instances_client=self.instances_client,
            zone_operations_client=self.zone_operations_client,
            project_id=self.gcp_config.project_id,
            zone=job.location,
            instance_name=request_id,
        )
        return RequestHead(
            job_id=job.job_id,
            status=instance_status,
            message=None,
        )

    # TODO: This function is deprecated and will be deleted in 0.11.x
    def get_instance_type(self, job: Job, region: Optional[str]) -> Optional[InstanceType]:
        return _choose_instance_type(
            machine_types_client=self.machine_types_client,
            accelerator_types_client=self.accelerator_types_client,
            project_id=self.gcp_config.project_id,
            zone=self.gcp_config.zone,
            requirements=job.requirements,
        )

    def get_supported_instances(self) -> List[InstanceType]:
        instances = {}
        for row in read_catalog_csv("gcp.csv"):
            if row["location"][:-2] not in self.gcp_config.regions:
                continue
            if row["spot"] == "True":  # any instance could be spot
                continue
            instance_key = row["instance_name"]
            gpus = []
            if int(row["gpu_count"]) > 0:
                instance_key += f'-{row["gpu_count"]}x{row["gpu_name"]}-{row["gpu_memory"]}'
                gpus = [
                    Gpu(
                        name=row["gpu_name"],
                        memory_mib=round(float(row["gpu_memory"]) * 1024),
                    )
                    for _ in range(int(row["gpu_count"]))
                ]

            if instance_key not in instances:
                instance = InstanceType(
                    instance_name=row["instance_name"],
                    resources=Resources(
                        cpus=int(row["cpu"]),
                        memory_mib=round(float(row["memory"]) * 1024),
                        gpus=gpus,
                        spot=True,
                        local=False,
                    ),
                    available_regions=[],
                )
                instances[instance_key] = instance
            if row["location"][:-2] not in instances[instance_key].available_regions:
                instances[instance_key].available_regions.append(row["location"][:-2])
        return list(instances.values())

    def run_instance(
        self, job: Job, instance_type: InstanceType, region: str
    ) -> LaunchedInstanceInfo:
        zones = _get_instance_zones(instance_type, region)
        return _run_instance(
            instances_client=self.instances_client,
            firewalls_client=self.firewalls_client,
            images_client=self.images_client,
            credentials=self.credentials,
            gcp_config=self.gcp_config,
            job=job,
            instance_type=instance_type,
            zones=zones,
        )

    def restart_instance(self, job: Job):
        _restart_instance(
            client=self.instances_client,
            gcp_config=_config_with_zone(self.gcp_config, job.location),
            instance_name=job.request_id,
        )
        return LaunchedInstanceInfo(request_id=job.request_id, location=job.location)

    def terminate_instance(self, runner: Runner):
        _terminate_instance(
            client=self.instances_client,
            gcp_config=_config_with_zone(self.gcp_config, runner.job.location),
            instance_name=runner.request_id,
        )

    def cancel_spot_request(self, runner: Runner):
        _terminate_instance(
            client=self.instances_client,
            gcp_config=_config_with_zone(self.gcp_config, runner.job.location),
            instance_name=runner.request_id,
        )

    def create_gateway(self, instance_name: str, ssh_key_pub: str, region: str) -> GatewayHead:
        instance = gateway.create_gateway_instance(
            instances_client=self.instances_client,
            firewalls_client=self.firewalls_client,
            project_id=self.gcp_config.project_id,
            network=_get_network_resource(self.gcp_config.vpc),
            subnet=_get_subnet_resource(region, self.gcp_config.subnet),
            zone=_get_zones(self.regions_client, self.gcp_config.project_id, [region])[0],
            instance_name=instance_name,
            service_account=self.credentials.service_account_email,
            labels=dict(
                role="gateway",
                owner="dstack",
            ),
            ssh_key_pub=ssh_key_pub,
        )
        return GatewayHead(
            instance_name=instance_name,
            external_ip=instance.network_interfaces[0].access_configs[0].nat_i_p,
            internal_ip=instance.network_interfaces[0].network_i_p,
            region=region,
        )

    def delete_instance(self, instance_name: str, region: str = None):
        _terminate_instance(
            client=self.instances_client,
            gcp_config=self.gcp_config,
            instance_name=instance_name,
        )

    def get_availability(self, offers: List[InstancePricing]) -> List[InstanceOffer]:
        quotas = {region: {} for region in self.gcp_config.regions}
        for region in self.regions_client.list(project=self.gcp_config.project_id):
            if region.name not in self.gcp_config.regions:
                continue
            for quota in region.quotas:
                quotas[region.name][quota.metric] = quota.limit - quota.usage

        availability_offers = []
        for offer in offers:
            if offer.region not in self.gcp_config.regions:
                continue
            availability = InstanceAvailability.UNKNOWN
            if not _has_gpu_quota(quotas[offer.region], offer.instance.resources):
                availability = InstanceAvailability.NO_QUOTA
            # todo quotas: cpu, memory, global gpu
            availability_offers.append(InstanceOffer(**offer.dict(), availability=availability))
        return availability_offers


def _config_with_zone(config: GCPConfig, zone: str) -> GCPConfig:
    new_config = config.copy()
    new_config.zone = zone
    new_config.region = gcp_utils.get_zone_region(zone)
    return new_config


def _get_instance_status(
    instances_client: compute_v1.InstancesClient,
    zone_operations_client: compute_v1.ZoneOperationsClient,
    project_id: str,
    zone: str,
    instance_name: str,
) -> RequestStatus:
    get_instance_request = compute_v1.GetInstanceRequest(
        instance=instance_name,
        project=project_id,
        zone=zone,
    )
    try:
        instance = instances_client.get(get_instance_request)
    except google.api_core.exceptions.NotFound:
        return RequestStatus.TERMINATED
    if instance.scheduling.provisioning_model == compute_v1.Scheduling.ProvisioningModel.SPOT.name:
        list_operations_request = compute_v1.ListZoneOperationsRequest(
            project=project_id,
            zone=zone,
            filter=f'(name = "{instance_name}") AND (operationType = "compute.instances.preempted")',
        )
        operations = zone_operations_client.list(list_operations_request)
        if len(list(operations)) > 0:
            return RequestStatus.NO_CAPACITY
    return RequestStatus.RUNNING


def _choose_instance_type(
    machine_types_client: compute_v1.MachineTypesClient,
    accelerator_types_client: compute_v1.AcceleratorTypesClient,
    project_id: str,
    zone: str,
    requirements: Optional[Requirements],
) -> Optional[InstanceType]:
    if requirements is None or requirements.gpus is None:
        return _get_nongpu_instance_type(
            machine_types_client=machine_types_client,
            project_id=project_id,
            zone=zone,
            requirements=requirements,
        )
    return _get_gpu_instance_type(
        machine_types_client=machine_types_client,
        accelerator_types_client=accelerator_types_client,
        project_id=project_id,
        zone=zone,
        requirements=requirements,
    )


def _get_nongpu_instance_type(
    machine_types_client: compute_v1.MachineTypesClient,
    project_id: str,
    zone: str,
    requirements: Optional[Requirements],
) -> Optional[InstanceType]:
    machine_families = ["e2-medium", "e2-standard-*", "e2-highmem-*", "e2-highcpu-*", "m1-*"]
    instance_types = _list_instance_types(
        machine_types_client=machine_types_client,
        project_id=project_id,
        zone=zone,
        machine_families=machine_families,
    )
    return choose_instance_type(instance_types, requirements)


def _get_gpu_instance_type(
    machine_types_client: compute_v1.MachineTypesClient,
    accelerator_types_client: compute_v1.AcceleratorTypesClient,
    project_id: str,
    zone: str,
    requirements: Requirements,
) -> InstanceType:
    # To create a GPU instance in GCP, we need to create a n1-* instance
    # and attach an accelerator to it. The only exception are a2-* instances
    # that already come with A100 accelerators.
    instance_types_without_gpus = _list_instance_types(
        machine_types_client=machine_types_client,
        project_id=project_id,
        zone=zone,
        machine_families=["n1-*"],
    )
    instance_types_without_gpus = [
        it
        for it in instance_types_without_gpus
        if it.instance_name not in ["n1-standard-1", "n1-highcpu-2"]
    ]
    instance_type = choose_instance_type(
        instance_types=instance_types_without_gpus,
        requirements=Requirements(
            cpus=requirements.cpus,
            memory_mib=requirements.memory_mib,
            shm_size_mib=requirements.shm_size_mib,
            spot=requirements.spot,
            local=requirements.local,
            gpus=None,
        ),
    )
    instance_types_with_gpus = []
    if instance_type is not None:
        instance_types_with_gpus.extend(
            _add_gpus_to_instance_type(
                accelerator_types_client=accelerator_types_client,
                project_id=project_id,
                zone=zone,
                instance_type=instance_type,
                requirements=requirements,
            )
        )
    instance_types_with_gpus.extend(
        _list_instance_types(
            machine_types_client=machine_types_client,
            project_id=project_id,
            zone=zone,
            machine_families=["a2-*", "g2-*"],  # A100, L4
        )
    )
    return choose_instance_type(instance_types_with_gpus, requirements)


def _list_instance_types(
    machine_types_client: compute_v1.MachineTypesClient,
    project_id: str,
    zone: str,
    machine_families: List[str],
) -> List[InstanceType]:
    machine_types = _list_machine_types(
        machine_types_client=machine_types_client,
        project_id=project_id,
        zone=zone,
        machine_families=machine_families,
    )
    return [_machine_type_to_instance_type(mt) for mt in machine_types]


def _list_machine_types(
    machine_types_client: compute_v1.MachineTypesClient,
    project_id: str,
    zone: str,
    machine_families: List[str],
) -> List[compute_v1.MachineType]:
    list_machine_types_request = compute_v1.ListMachineTypesRequest()
    list_machine_types_request.project = project_id
    list_machine_types_request.zone = zone
    list_machine_types_request.filter = " OR ".join(f"(name = {mf})" for mf in machine_families)
    machine_types = machine_types_client.list(list_machine_types_request)
    return [mt for mt in machine_types if not mt.deprecated.state == "DEPRECATED"]


def _machine_type_to_instance_type(machine_type: compute_v1.MachineType) -> InstanceType:
    gpus = []
    for acc in machine_type.accelerators:
        gpus.extend(
            [
                Gpu(
                    name=_accelerator_name_to_gpu_name(acc.guest_accelerator_type),
                    memory_mib=_get_gpu_memory(acc.guest_accelerator_type),
                )
                for _ in range(acc.guest_accelerator_count)
            ]
        )
    return InstanceType(
        instance_name=machine_type.name,
        resources=Resources(
            cpus=machine_type.guest_cpus,
            memory_mib=machine_type.memory_mb,
            gpus=gpus,
            spot=True,
            local=False,
        ),
    )


def _get_gpu_memory(accelerator_name: str) -> int:
    for acc in _supported_accelerators:
        if acc["accelerator_name"] == accelerator_name:
            return acc["memory_mb"]


def _add_gpus_to_instance_type(
    accelerator_types_client: compute_v1.AcceleratorTypesClient,
    project_id: str,
    zone: str,
    instance_type: InstanceType,
    requirements: Requirements,
) -> List[InstanceType]:
    accelerator_types = _list_accelerator_types(
        accelerator_types_client=accelerator_types_client,
        project_id=project_id,
        zone=zone,
        accelerator_families=[
            "nvidia-tesla-t4",
            "nvidia-tesla-v100",
            "nvidia-tesla-p100",
        ],
    )
    return _instances_x_accelerators([instance_type], accelerator_types)


def _instances_x_accelerators(
    instances: List[InstanceType], accelerators: List[compute_v1.AcceleratorType]
) -> List[InstanceType]:
    pow2 = [2**i for i in range(4)]
    combined = []
    for accelerator in accelerators:
        for count in pow2:
            if count > accelerator.maximum_cards_per_instance:
                continue
            max_vcpu = _get_max_vcpu_per_accelerator(accelerator.name, count)
            max_ram_mb = _get_max_ram_per_accelerator(accelerator.name, count)
            for instance in instances:
                if (
                    max_vcpu < instance.resources.cpus
                    or max_ram_mb < instance.resources.memory_mib
                ):
                    continue
                combined.append(_attach_accelerator(instance, accelerator, count))
    return combined


def _attach_accelerator(
    instance: InstanceType, accelerator: compute_v1.AcceleratorType, count: int
) -> InstanceType:
    data = instance.dict()
    data["resources"]["gpus"] = [
        Gpu(
            name=_accelerator_name_to_gpu_name(accelerator.name),
            memory_mib=_get_gpu_memory(accelerator.name),
        )
        for _ in range(count)
    ]
    return InstanceType.parse_obj(data)


def _list_accelerator_types(
    accelerator_types_client: compute_v1.AcceleratorTypesClient,
    project_id: str,
    zone: str,
    accelerator_families: List[str],
) -> List[compute_v1.AcceleratorType]:
    list_accelerator_types_request = compute_v1.ListAcceleratorTypesRequest()
    list_accelerator_types_request.project = project_id
    list_accelerator_types_request.zone = zone
    list_accelerator_types_request.filter = " OR ".join(
        f"(name = {af})" for af in accelerator_families
    )
    accelerator_types = accelerator_types_client.list(list_accelerator_types_request)
    return [at for at in accelerator_types]


def _accelerator_name_to_gpu_name(accelerator_name: str) -> str:
    for acc in _supported_accelerators:
        if acc["accelerator_name"] == accelerator_name:
            return acc["gpu_name"]


def _gpu_to_accelerator_name(gpu: Gpu) -> str:
    for acc in _supported_accelerators:
        if acc["gpu_name"] == gpu.name and acc["memory_mb"] == gpu.memory_mib:
            return acc["accelerator_name"]


def _get_max_vcpu_per_accelerator(accelerator_name: str, count: int) -> int:
    for acc in _supported_accelerators:
        if acc["accelerator_name"] == accelerator_name:
            return acc["max_vcpu"][count]


def _get_max_ram_per_accelerator(accelerator_name: str, count: int) -> int:
    for acc in _supported_accelerators:
        if acc["accelerator_name"] == accelerator_name:
            return acc["max_ram_mb"][count]


def _get_image_name(
    images_client: compute_v1.ImagesClient, instance_type: InstanceType
) -> Optional[str]:
    image_prefix = "dstack-"
    if len(instance_type.resources.gpus) > 0:
        image_prefix += "cuda-"
    image_prefix += version.base_image.replace(".", "-")

    list_request = compute_v1.ListImagesRequest()
    list_request.project = "dstack"
    list_request.order_by = "creationTimestamp desc"
    images = images_client.list(list_request)
    for image in images:
        # Specifying both a list filter and sort order is not currently supported in compute_v1
        # so we don't use list_request.filter to filter images
        if image.name.startswith(image_prefix):
            return image.name
    return None


def _get_user_data_script(gcp_config: GCPConfig, job: Job, instance_type: InstanceType) -> str:
    config_content = gcp_config.serialize_yaml().replace("\n", "\\n")
    runner_content = serialize_runner_yaml(job.runner_id, instance_type.resources, 3000, 4000)
    return f"""#cloud-config

cloud_final_modules:
- [scripts-user, always]

runcmd:
    - |
        if [ ! -f /root/.dstack/booted ]; then
            mkdir -p /root/.dstack/
            echo '{config_content}' > /root/.dstack/{BACKEND_CONFIG_FILENAME}
            echo '{runner_content}' > /root/.dstack/{RUNNER_CONFIG_FILENAME}
            {get_dstack_runner()}
            touch /root/.dstack/booted
        fi
        HOME=/root nohup dstack-runner --log-level 6 start --http-port {WS_PORT}
"""


def _get_accelerator_configs(
    project_id: str, zone: str, instance_type: InstanceType
) -> List[compute_v1.AcceleratorConfig]:
    if instance_type.instance_name.startswith("a2") or len(instance_type.resources.gpus) == 0:
        return []
    accelerator_config = compute_v1.AcceleratorConfig()
    accelerator_config.accelerator_count = len(instance_type.resources.gpus)
    accelerator_name = _gpu_to_accelerator_name(instance_type.resources.gpus[0])
    accelerator_config.accelerator_type = (
        f"projects/{project_id}/zones/{zone}/acceleratorTypes/{accelerator_name}"
    )
    return [accelerator_config]


def _get_network_resource(vpc: str) -> str:
    return f"global/networks/{vpc}"


def _get_subnet_resource(region: str, subnet: str) -> str:
    return f"regions/{region}/subnetworks/{subnet}"


def _get_labels(bucket: str, job: Job) -> Dict[str, str]:
    labels = {
        "owner": "dstack",
    }
    if gcp_utils.is_valid_label_value(bucket):
        labels["dstack_bucket"] = bucket
    dstack_repo = job.repo.repo_id.lower().replace(".", "-")
    if gcp_utils.is_valid_label_value(dstack_repo):
        labels["dstack_repo"] = dstack_repo
    dstack_user_name = job.hub_user_name.lower().replace(" ", "_")
    if gcp_utils.is_valid_label_value(dstack_user_name):
        labels["dstack_user_name"] = dstack_user_name
    return labels


def _run_instance(
    instances_client: compute_v1.InstancesClient,
    firewalls_client: compute_v1.FirewallsClient,
    images_client: compute_v1.ImagesClient,
    credentials: service_account.Credentials,
    gcp_config: GCPConfig,
    job: Job,
    instance_type: InstanceType,
    zones: List[str],
) -> LaunchedInstanceInfo:
    for zone in zones:
        try:
            logger.info(
                "Requesting %s %s instance in %s...",
                instance_type.instance_name,
                "spot" if job.requirements.spot else "",
                zone,
            )
            instance = _launch_instance(
                instances_client=instances_client,
                firewalls_client=firewalls_client,
                project_id=gcp_config.project_id,
                zone=zone,
                network=_get_network_resource(gcp_config.vpc),
                subnet=_get_subnet_resource(gcp_utils.get_zone_region(zone), gcp_config.subnet),
                machine_type=instance_type.instance_name,
                image_name=_get_image_name(
                    images_client=images_client,
                    instance_type=instance_type,
                ),
                instance_name=job.instance_name,
                user_data_script=_get_user_data_script(
                    gcp_config=_config_with_zone(gcp_config, zone),
                    job=job,
                    instance_type=instance_type,
                ),
                service_account=credentials.service_account_email,
                spot=instance_type.resources.spot,
                accelerators=_get_accelerator_configs(
                    project_id=gcp_config.project_id,
                    zone=zone,
                    instance_type=instance_type,
                ),
                labels=_get_labels(
                    bucket=gcp_config.bucket_name,
                    job=job,
                ),
                ssh_key_pub=job.ssh_key_pub,
            )
            logger.info("Request succeeded")
            return LaunchedInstanceInfo(request_id=instance.name, location=zone)
        except NoCapacityError:
            logger.info("Failed to request instance in %s", zone)
    raise NoCapacityError()


def _get_zones(
    regions_client: compute_v1.RegionsClient,
    project_id: str,
    configured_regions: List[str],
) -> List[str]:
    regions = regions_client.list(project=project_id)
    zones = [
        gcp_utils.get_resource_name(z)
        for r in regions
        for z in r.zones
        if r.name in configured_regions
    ]
    return zones


def _launch_instance(
    instances_client: compute_v1.InstancesClient,
    firewalls_client: compute_v1.FirewallsClient,
    project_id: str,
    network: str,
    subnet: str,
    zone: str,
    image_name: str,
    machine_type: str,
    instance_name: str,
    user_data_script: str,
    service_account: str,
    spot: bool,
    accelerators: List[compute_v1.AcceleratorConfig],
    labels: Dict[str, str],
    ssh_key_pub: str,
) -> compute_v1.Instance:
    try:
        _create_firewall_rules(
            firewalls_client=firewalls_client,
            project_id=project_id,
            network=network,
        )
    except google.api_core.exceptions.Conflict:
        pass
    disk = _disk_from_image(
        disk_type=f"zones/{zone}/diskTypes/pd-balanced",
        disk_size_gb=100,
        boot=True,
        source_image=f"projects/dstack/global/images/{image_name}",
        auto_delete=True,
    )
    instance = _create_instance(
        instances_client=instances_client,
        project_id=project_id,
        zone=zone,
        network_link=network,
        subnetwork_link=subnet,
        machine_type=machine_type,
        instance_name=instance_name,
        disks=[disk],
        user_data_script=user_data_script,
        service_account=service_account,
        external_access=True,
        spot=spot,
        accelerators=accelerators,
        labels=labels,
        ssh_key_pub=ssh_key_pub,
    )
    return instance


def _disk_from_image(
    disk_type: str,
    disk_size_gb: int,
    boot: bool,
    source_image: str,
    auto_delete: bool = True,
) -> compute_v1.AttachedDisk:
    """
    Create an AttachedDisk object to be used in VM instance creation. Uses an image as the
    source for the new disk.

    Args:
         disk_type: the type of disk you want to create. This value uses the following format:
            "zones/{zone}/diskTypes/(pd-standard|pd-ssd|pd-balanced|pd-extreme)".
            For example: "zones/us-west3-b/diskTypes/pd-ssd"
        disk_size_gb: size of the new disk in gigabytes
        boot: boolean flag indicating whether this disk should be used as a boot disk of an instance
        source_image: source image to use when creating this disk. You must have read access to this disk. This can be one
            of the publicly available images or an image from one of your projects.
            This value uses the following format: "projects/{project_name}/global/images/{image_name}"
        auto_delete: boolean flag indicating whether this disk should be deleted with the VM that uses it

    Returns:
        AttachedDisk object configured to be created using the specified image.
    """
    boot_disk = compute_v1.AttachedDisk()
    initialize_params = compute_v1.AttachedDiskInitializeParams()
    initialize_params.source_image = source_image
    initialize_params.disk_size_gb = disk_size_gb
    initialize_params.disk_type = disk_type
    boot_disk.initialize_params = initialize_params
    # Remember to set auto_delete to True if you want the disk to be deleted when you delete
    # your VM instance.
    boot_disk.auto_delete = auto_delete
    boot_disk.boot = boot
    return boot_disk


def _create_instance(
    instances_client: compute_v1.InstancesClient,
    project_id: str,
    zone: str,
    instance_name: str,
    disks: List[compute_v1.AttachedDisk],
    ssh_key_pub: str,
    machine_type: str = "n1-standard-1",
    network_link: str = "global/networks/default",
    subnetwork_link: str = None,
    internal_ip: str = None,
    external_access: bool = False,
    external_ipv4: str = None,
    accelerators: List[compute_v1.AcceleratorConfig] = None,
    spot: bool = False,
    instance_termination_action: str = "STOP",
    custom_hostname: str = None,
    delete_protection: bool = False,
    user_data_script: Optional[str] = None,
    service_account: Optional[str] = None,
    labels: Optional[Dict[str, str]] = None,
) -> compute_v1.Instance:
    """
    Send an instance creation request to the Compute Engine API and wait for it to complete.

    Args:
        project_id: project ID or project number of the Cloud project you want to use.
        zone: name of the zone to create the instance in. For example: "us-west3-b"
        instance_name: name of the new virtual machine (VM) instance.
        disks: a list of compute_v1.AttachedDisk objects describing the disks
            you want to attach to your new instance.
        machine_type: machine type of the VM being created. This value uses the
            following format: "zones/{zone}/machineTypes/{type_name}".
            For example: "zones/europe-west3-c/machineTypes/f1-micro"
        network_link: name of the network you want the new instance to use.
            For example: "global/networks/default" represents the network
            named "default", which is created automatically for each project.
        subnetwork_link: name of the subnetwork you want the new instance to use.
            This value uses the following format:
            "regions/{region}/subnetworks/{subnetwork_name}"
        internal_ip: internal IP address you want to assign to the new instance.
            By default, a free address from the pool of available internal IP addresses of
            used subnet will be used.
        external_access: boolean flag indicating if the instance should have an external IPv4
            address assigned.
        external_ipv4: external IPv4 address to be assigned to this instance. If you specify
            an external IP address, it must live in the same region as the zone of the instance.
            This setting requires `external_access` to be set to True to work.
        accelerators: a list of AcceleratorConfig objects describing the accelerators that will
            be attached to the new instance.
        spot: boolean value indicating if the new instance should be a Spot VM or not.
        instance_termination_action: What action should be taken once a Spot VM is terminated.
            Possible values: "STOP", "DELETE"
        custom_hostname: Custom hostname of the new VM instance.
            Custom hostnames must conform to RFC 1035 requirements for valid hostnames.
        delete_protection: boolean value indicating if the new virtual machine should be
            protected against deletion or not.
    Returns:
        Instance object.
    """
    network_interface = compute_v1.NetworkInterface()
    network_interface.name = network_link
    if subnetwork_link:
        network_interface.subnetwork = subnetwork_link

    if internal_ip:
        network_interface.network_i_p = internal_ip

    if external_access:
        access = compute_v1.AccessConfig()
        access.type_ = compute_v1.AccessConfig.Type.ONE_TO_ONE_NAT.name
        access.name = "External NAT"
        access.network_tier = access.NetworkTier.PREMIUM.name
        if external_ipv4:
            access.nat_i_p = external_ipv4
        network_interface.access_configs = [access]

    instance = compute_v1.Instance()
    instance.network_interfaces = [network_interface]
    instance.name = instance_name
    instance.disks = disks
    if re.match(r"^zones/[a-z\d\-]+/machineTypes/[a-z\d\-]+$", machine_type):
        instance.machine_type = machine_type
    else:
        instance.machine_type = f"zones/{zone}/machineTypes/{machine_type}"

    if accelerators:
        instance.guest_accelerators = accelerators

    if accelerators or "a2-" in machine_type:
        instance.scheduling.on_host_maintenance = "TERMINATE"

    if spot:
        instance.scheduling = compute_v1.Scheduling()
        instance.scheduling.provisioning_model = compute_v1.Scheduling.ProvisioningModel.SPOT.name
        instance.scheduling.instance_termination_action = instance_termination_action

    if custom_hostname is not None:
        instance.hostname = custom_hostname

    if delete_protection:
        instance.deletion_protection = True

    metadata_items = [compute_v1.Items(key="ssh-keys", value=f"ubuntu:{ssh_key_pub}")]
    if user_data_script is not None:
        metadata_items.append(compute_v1.Items(key="user-data", value=user_data_script))
    instance.metadata = compute_v1.Metadata(items=metadata_items)

    if service_account is not None:
        instance.service_accounts = [
            compute_v1.ServiceAccount(
                email=service_account,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
        ]

    if labels is not None:
        instance.labels = labels

    instance.tags = compute_v1.Tags(items=[DSTACK_INSTANCE_TAG])

    request = compute_v1.InsertInstanceRequest()
    request.zone = zone
    request.project = project_id
    request.instance_resource = instance

    operation = instances_client.insert(request=request)
    try:
        gcp_utils.wait_for_extended_operation(operation, "instance creation")
    except google.api_core.exceptions.ServiceUnavailable:
        raise NoCapacityError()

    return instances_client.get(project=project_id, zone=zone, instance=instance_name)


def _create_firewall_rules(
    firewalls_client: compute_v1.FirewallsClient,
    project_id: str,
    network: str = "global/networks/default",
):
    """
    Creates a simple firewall rule allowing for incoming SSH access from the entire Internet.

    Args:
        project_id: project ID or project number of the Cloud project you want to use.
        firewall_rule_name: name of the rule that is created.
        network: name of the network the rule will be applied to. Available name formats:
            * https://www.googleapis.com/compute/v1/projects/{project_id}/global/networks/{network}
            * projects/{project_id}/global/networks/{network}
            * global/networks/{network}

    Returns:
        A Firewall object.
    """
    firewall_rule = compute_v1.Firewall()
    firewall_rule.name = f"dstack-ssh-in-" + network.replace("/", "-")
    firewall_rule.direction = "INGRESS"

    allowed_ssh_port = compute_v1.Allowed()
    allowed_ssh_port.I_p_protocol = "tcp"
    allowed_ssh_port.ports = ["22"]

    firewall_rule.allowed = [allowed_ssh_port]
    firewall_rule.source_ranges = ["0.0.0.0/0"]
    firewall_rule.network = network
    firewall_rule.description = "Allowing only SSH connections from Internet."

    firewall_rule.target_tags = [DSTACK_INSTANCE_TAG]

    operation = firewalls_client.insert(project=project_id, firewall_resource=firewall_rule)
    gcp_utils.wait_for_extended_operation(operation, "firewall rule creation")


RESTART_ATTEMPTS = 5
RESTART_WAIT = 5


def _restart_instance(
    client: compute_v1.InstancesClient, gcp_config: GCPConfig, instance_name: str
):
    request = compute_v1.StartInstanceRequest(
        instance=instance_name,
        project=gcp_config.project_id,
        zone=gcp_config.zone,
    )
    for _ in range(RESTART_ATTEMPTS):
        try:
            operation = client.start(request)
        except google.api_core.exceptions.NotFound:
            raise InstanceNotFoundError()
        try:
            gcp_utils.wait_for_extended_operation(operation)
            return
        except google.api_core.exceptions.BadRequest:
            logger.warning(
                "Start instance request failed. Instance may still be transitioning to stopped state. Reattempting..."
            )
            time.sleep(RESTART_WAIT)
            continue
    raise BackendValueError("Failed to restart instance. Try later.")


def _terminate_instance(
    client: compute_v1.InstancesClient, gcp_config: GCPConfig, instance_name: str
):
    request = compute_v1.AggregatedListInstancesRequest()
    request.project = gcp_config.project_id
    request.filter = f"name eq {instance_name}"
    request.max_results = 1
    agg_list = client.aggregated_list(request=request)
    for zone, response in agg_list:
        for _ in response.instances:
            _delete_instance(
                client=client,
                instance_name=instance_name,
                project_id=gcp_config.project_id,
                zone=zone[6:],  # strip zones/
            )


def _delete_instance(
    client: compute_v1.InstancesClient, project_id: str, zone: str, instance_name: str
):
    delete_request = compute_v1.DeleteInstanceRequest(
        instance=instance_name,
        project=project_id,
        zone=zone,
    )
    try:
        client.delete(delete_request)
    except google.api_core.exceptions.NotFound:
        pass


def _has_gpu_quota(quotas: Dict[str, int], resources: Resources) -> bool:
    if not resources.gpus:
        return True
    gpu = resources.gpus[0]
    quota_name = f"NVIDIA_{gpu.name}_GPUS"
    if gpu.name == "A100" and gpu.memory_mib == 80 * 1024:
        quota_name = "NVIDIA_A100_80GB_GPUS"
    if resources.spot:
        quota_name = "PREEMPTIBLE_" + quota_name
    return len(resources.gpus) <= quotas.get(quota_name, 0)


def _get_instance_zones(instance_type: InstanceType, region: str) -> List[str]:
    zones = []
    for row in read_catalog_csv("gcp.csv"):
        if row["location"][:-2] != region:
            continue
        if row["instance_name"] != instance_type.instance_name:
            continue
        if row["spot"] != str(instance_type.resources.spot):
            continue
        # n1- instances could have a wide range of GPUs attached to them
        if int(row["gpu_count"]) != len(instance_type.resources.gpus):
            continue
        if instance_type.resources.gpus:
            if row["gpu_name"] != instance_type.resources.gpus[0].name:
                continue
            if not math.isclose(
                float(row["gpu_memory"]),
                instance_type.resources.gpus[0].memory_mib / 1024,
                rel_tol=1e-5,
            ):
                continue
        zones.append(row["location"])
    return zones
