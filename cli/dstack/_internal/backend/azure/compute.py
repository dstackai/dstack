import base64
import re
from collections import namedtuple
from operator import attrgetter
from typing import List, Optional, Tuple

from azure.core.credentials import TokenCredential
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.mgmt.authorization import AuthorizationManagementClient
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.compute.models import (
    DiskCreateOptionTypes,
    HardwareProfile,
    ImageReference,
    InstanceViewStatus,
    LinuxConfiguration,
    ManagedDiskParameters,
    NetworkProfile,
    OSDisk,
    OSProfile,
    ResourceIdentityType,
    ResourceSku,
    SshConfiguration,
    SshPublicKey,
    StorageAccountTypes,
    StorageProfile,
    SubResource,
    UserAssignedIdentitiesValue,
    VirtualMachine,
    VirtualMachineIdentity,
    VirtualMachineNetworkInterfaceConfiguration,
    VirtualMachineNetworkInterfaceIPConfiguration,
    VirtualMachinePublicIPAddressConfiguration,
)
from azure.mgmt.keyvault import KeyVaultManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.resource import ResourceManagementClient
from msrestazure.tools import parse_resource_id

import dstack._internal.backend.azure.gateway as gateway
from dstack import version
from dstack._internal.backend.azure import utils as azure_utils
from dstack._internal.backend.azure.config import AzureConfig
from dstack._internal.backend.base.compute import (
    WS_PORT,
    Compute,
    NoCapacityError,
    choose_instance_type,
    get_dstack_runner,
)
from dstack._internal.backend.base.config import BACKEND_CONFIG_FILENAME, RUNNER_CONFIG_FILENAME
from dstack._internal.backend.base.runners import serialize_runner_yaml
from dstack._internal.core.gateway import GatewayHead
from dstack._internal.core.instance import (
    InstanceAvailability,
    InstanceOffer,
    InstancePricing,
    InstanceType,
    LaunchedInstanceInfo,
)
from dstack._internal.core.job import Job
from dstack._internal.core.request import RequestHead, RequestStatus
from dstack._internal.core.runners import Gpu, Resources, Runner
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

VMSeries = namedtuple("VMSeries", ["pattern", "gpu_name", "gpu_memory"])
vm_series = [
    VMSeries(r"D(\d+)s_v3", None, None),  # Dsv3-series
    VMSeries(r"E(\d+)i?s_v4", None, None),  # Esv4-series
    VMSeries(r"E(\d+)-(\d+)s_v4", None, None),  # Esv4-series (constrained vCPU)
    VMSeries(r"NC(\d+)s_v3", "V100", 16 * 1024),  # NCv3-series [V100 16GB]
    VMSeries(r"NC(\d+)as_T4_v3", "T4", 16 * 1024),  # NCasT4_v3-series [T4]
    VMSeries(r"ND(\d+)rs_v2", "V100", 32 * 1024),  # NDv2-series [8xV100 32GB]
    VMSeries(r"NV(\d+)adm?s_A10_v5", "A10", 24 * 1024),  # NVadsA10 v5-series [A10]
    VMSeries(r"NC(\d+)ads_A100_v4", "A100", 80 * 1024),  # NC A100 v4-series [A100 80GB]
    VMSeries(r"ND(\d+)asr_v4", "A100", 40 * 1024),  # ND A100 v4-series [8xA100 40GB]
    VMSeries(r"ND(\d+)amsr_A100_v4", "A100", 80 * 1024),  # NDm A100 v4-series [8xA100 80GB]
]


class AzureCompute(Compute):
    def __init__(
        self,
        credential: TokenCredential,
        azure_config: AzureConfig,
    ):
        self.azure_config = azure_config
        self._compute_client = ComputeManagementClient(
            credential=credential, subscription_id=self.azure_config.subscription_id
        )
        self._resource_client = ResourceManagementClient(
            credential=credential, subscription_id=self.azure_config.subscription_id
        )
        self._network_client = NetworkManagementClient(
            credential=credential, subscription_id=self.azure_config.subscription_id
        )
        self._authorization_client = AuthorizationManagementClient(
            credential=credential, subscription_id=self.azure_config.subscription_id
        )
        self._keyvault_client = KeyVaultManagementClient(
            credential=credential, subscription_id=self.azure_config.subscription_id
        )
        self._storage_account_id = azure_utils.get_storage_account_id(
            self.azure_config.subscription_id,
            self.azure_config.resource_group,
            self.azure_config.storage_account,
        )

    # TODO: This function is deprecated and will be deleted in 0.11.x
    def get_instance_type(self, job: Job, region_name: Optional[str]) -> Optional[InstanceType]:
        instance_types = _get_instance_types(
            client=self._compute_client, location=region_name or self.azure_config.locations[0]
        )
        return choose_instance_type(instance_types=instance_types, requirements=job.requirements)

    def get_supported_instances(self) -> List[InstanceType]:
        instances = {}
        for location in self.azure_config.locations:
            for i in _get_instance_types(client=self._compute_client, location=location):
                if i.instance_name not in instances:
                    instances[i.instance_name] = i
                    i.available_regions = []
                instances[i.instance_name].available_regions.append(location)
        return list(instances.values())

    def run_instance(
        self, job: Job, instance_type: InstanceType, region: str
    ) -> LaunchedInstanceInfo:
        return _run_instance(
            compute_client=self._compute_client,
            azure_config=self.azure_config,
            job=job,
            instance_type=instance_type,
            location=region,
        )

    def get_request_head(self, job: Job, request_id: Optional[str]) -> RequestHead:
        if request_id is None:
            return RequestHead(
                job_id=job.job_id,
                status=RequestStatus.TERMINATED,
                message="request_id is not specified",
            )
        instance_status = _get_instance_status(
            compute_client=self._compute_client,
            resource_group=self.azure_config.resource_group,
            instance_name=request_id,
        )
        return RequestHead(
            job_id=job.job_id,
            status=instance_status,
            message=None,
        )

    def terminate_instance(self, runner: Runner):
        _terminate_instance(
            compute_client=self._compute_client,
            resource_group=self.azure_config.resource_group,
            instance_name=runner.request_id,
        )

    def cancel_spot_request(self, runner: Runner):
        self.terminate_instance(runner)

    def create_gateway(self, instance_name: str, ssh_key_pub: str, region: str) -> GatewayHead:
        location = region
        vm = gateway.create_gateway(
            storage_account=self.azure_config.storage_account,
            compute_client=self._compute_client,
            network_client=self._network_client,
            subscription_id=self.azure_config.subscription_id,
            location=location,
            resource_group=self.azure_config.resource_group,
            network=azure_utils.get_default_network_name(
                storage_account=self.azure_config.storage_account,
                location=location,
            ),
            subnet=azure_utils.get_default_subnet_name(
                storage_account=self.azure_config.storage_account,
                location=location,
            ),
            instance_name=instance_name,
            ssh_key_pub=ssh_key_pub,
        )
        interface = gateway.get_network_interface(
            network_client=self._network_client,
            resource_group=self.azure_config.resource_group,
            interface=parse_resource_id(vm.network_profile.network_interfaces[0].id)[
                "resource_name"
            ],
        )
        public_ip = interface.ip_configurations[0].public_ip_address.ip_address
        return GatewayHead(
            instance_name=instance_name,
            external_ip=public_ip,
            internal_ip=interface.ip_configurations[0].private_ip_address,
            region=location,
        )

    def delete_instance(self, instance_name: str, region: str = None):
        _terminate_instance(
            compute_client=self._compute_client,
            resource_group=self.azure_config.resource_group,
            instance_name=instance_name,
        )

    def get_availability(self, offers: List[InstancePricing]) -> List[InstanceOffer]:
        availability_offers = {}
        locations = set()
        for offer in offers:
            location = offer.region
            if location not in self.azure_config.locations:
                continue
            locations.add(location)
            instance_name = offer.instance.instance_name
            spot = offer.instance.resources.spot
            availability_offers[(instance_name, location, spot)] = InstanceOffer(
                **offer.dict(), availability=InstanceAvailability.NO_QUOTA
            )

        for location in locations:
            resources = self._compute_client.resource_skus.list(filter=f"location eq '{location}'")
            for resource in resources:
                if resource.resource_type != "virtualMachines" or not _vm_type_available(resource):
                    continue
                for spot in (True, False):
                    key = (resource.name, location, spot)
                    if key in availability_offers:
                        availability_offers[key].availability = InstanceAvailability.UNKNOWN
        return list(availability_offers.values())


def _get_instance_types(client: ComputeManagementClient, location: str) -> List[InstanceType]:
    instance_types = []
    vm_series_pattern = re.compile(
        f"^Standard_({'|'.join(series.pattern for series in vm_series)})$"
    )
    # Only location filter is supported currently in azure API.
    # See: https://learn.microsoft.com/en-us/python/api/azure-mgmt-compute/azure.mgmt.compute.v2021_07_01.operations.resourceskusoperations?view=azure-python#azure-mgmt-compute-v2021-07-01-operations-resourceskusoperations-list
    resources = client.resource_skus.list(filter=f"location eq '{location}'")
    for resource in resources:
        if resource.resource_type != "virtualMachines" or not _vm_type_available(resource):
            continue
        if re.match(vm_series_pattern, resource.name) is None:
            continue
        capabilities = {pair.name: pair.value for pair in resource.capabilities}
        gpus = []
        if "GPUs" in capabilities:
            gpu_name, gpu_memory = _get_gpu_name_memory(resource.name)
            gpus = [Gpu(name=gpu_name, memory_mib=gpu_memory)] * int(capabilities["GPUs"])
        instance_types.append(
            InstanceType(
                instance_name=resource.name,
                resources=Resources(
                    cpus=capabilities["vCPUs"],
                    memory_mib=int(float(capabilities["MemoryGB"]) * 1024),
                    gpus=gpus,
                    spot=True,
                    local=False,
                ),
            )
        )
    return instance_types


def _vm_type_available(vm_resource: ResourceSku) -> bool:
    if len(vm_resource.restrictions) == 0:
        return True
    # If a VM type is restricted in "Zone", it is still available in other zone.
    # Otherwise the restriction type is "Location"
    if vm_resource.restrictions[0].type == "Zone":
        return True
    return False


def _get_gpu_name_memory(vm_name: str) -> Tuple[str, int]:
    for pattern, gpu_name, gpu_memory in vm_series:
        m = re.match(f"^Standard_{pattern}$", vm_name)
        if m is None:
            continue
        if gpu_name == "A10":  # A10 could be shared (minimal is 1/6 for Standard_NV6ads_A10_v5)
            gpu_memory = (gpu_memory * int(m.group(1))) // 36
        return gpu_name, gpu_memory


def _run_instance(
    compute_client: ComputeManagementClient,
    azure_config: AzureConfig,
    job: Job,
    instance_type: InstanceType,
    location: str,
) -> LaunchedInstanceInfo:
    logger.info(
        "Requesting %s %s instance in %s...",
        instance_type.instance_name,
        "spot" if instance_type.resources.spot else "",
        location,
    )
    try:
        vm = _launch_instance(
            compute_client=compute_client,
            subscription_id=azure_config.subscription_id,
            location=location,
            resource_group=azure_config.resource_group,
            network_security_group=azure_utils.get_default_network_security_group_name(
                storage_account=azure_config.storage_account, location=location
            ),
            network=azure_utils.get_default_network_name(
                storage_account=azure_config.storage_account,
                location=location,
            ),
            subnet=azure_utils.get_default_subnet_name(
                storage_account=azure_config.storage_account,
                location=location,
            ),
            managed_identity=azure_utils.get_runner_managed_identity_name(
                storage_account=azure_config.storage_account
            ),
            image_reference=_get_image_ref(
                compute_client=compute_client,
                location=location,
                cuda=len(instance_type.resources.gpus) > 0,
            ),
            vm_size=instance_type.instance_name,
            instance_name=job.instance_name,
            user_data=_get_user_data_script(
                azure_config=_config_with_location(azure_config, location),
                job=job,
                instance_type=instance_type,
            ),
            ssh_pub_key=job.ssh_key_pub,
            spot=instance_type.resources.spot,
        )
        logger.info("Request succeeded")
        return LaunchedInstanceInfo(request_id=vm.name, location=location)
    except NoCapacityError:
        logger.info("Failed to request instance in %s", location)
    logger.info("Failed to request instance")
    raise NoCapacityError()


def _get_image_ref(
    compute_client: ComputeManagementClient,
    location: str,
    cuda: bool,
) -> ImageReference:
    image_name = "dstack-"
    if cuda:
        image_name += "cuda-"
    image_name += version.base_image

    image = compute_client.community_gallery_images.get(
        location=location,
        public_gallery_name="dstack-ebac134d-04b9-4c2b-8b6c-ad3e73904aa7",  # Gen2
        gallery_image_name=image_name,
    )
    return ImageReference(community_gallery_image_id=image.unique_id)


def _config_with_location(config: AzureConfig, location: str) -> AzureConfig:
    new_config = config.copy()
    new_config.network = azure_utils.get_default_network_name(config.storage_account, location)
    new_config.subnet = azure_utils.get_default_subnet_name(config.storage_account, location)
    return new_config


def _get_user_data_script(azure_config: AzureConfig, job: Job, instance_type: InstanceType) -> str:
    config_content = azure_config.serialize_yaml().replace("\n", "\\n")
    runner_content = serialize_runner_yaml(job.runner_id, instance_type.resources, 3000, 4000)
    return f"""#!/bin/sh
mkdir -p /root/.dstack/
echo '{config_content}' > /root/.dstack/{BACKEND_CONFIG_FILENAME}
echo '{runner_content}' > /root/.dstack/{RUNNER_CONFIG_FILENAME}
{get_dstack_runner()}
HOME=/root nohup dstack-runner --log-level 6 start --http-port {WS_PORT}
"""


def _launch_instance(
    compute_client: ComputeManagementClient,
    subscription_id: str,
    location: str,
    resource_group: str,
    network_security_group: str,
    network: str,
    subnet: str,
    managed_identity: str,
    image_reference: ImageReference,
    vm_size: str,
    instance_name: str,
    user_data: str,
    ssh_pub_key: str,
    spot: bool,
) -> VirtualMachine:
    try:
        poller = compute_client.virtual_machines.begin_create_or_update(
            resource_group,
            instance_name,
            VirtualMachine(
                location=location,
                hardware_profile=HardwareProfile(vm_size=vm_size),
                storage_profile=StorageProfile(
                    image_reference=image_reference,
                    os_disk=OSDisk(
                        create_option=DiskCreateOptionTypes.FROM_IMAGE,
                        managed_disk=ManagedDiskParameters(
                            storage_account_type=StorageAccountTypes.STANDARD_SSD_LRS
                        ),
                        disk_size_gb=100,
                        delete_option="Delete",
                    ),
                ),
                os_profile=OSProfile(
                    computer_name="runnervm",
                    admin_username="ubuntu",
                    linux_configuration=LinuxConfiguration(
                        ssh=SshConfiguration(
                            public_keys=[
                                SshPublicKey(
                                    path="/home/ubuntu/.ssh/authorized_keys",
                                    key_data=ssh_pub_key,
                                )
                            ]
                        )
                    ),
                ),
                network_profile=NetworkProfile(
                    network_api_version=NetworkManagementClient.DEFAULT_API_VERSION,
                    network_interface_configurations=[
                        VirtualMachineNetworkInterfaceConfiguration(
                            name="nic_config",
                            network_security_group=SubResource(
                                id=azure_utils.get_network_security_group_id(
                                    subscription_id,
                                    resource_group,
                                    network_security_group,
                                )
                            ),
                            ip_configurations=[
                                VirtualMachineNetworkInterfaceIPConfiguration(
                                    name="ip_config",
                                    subnet=SubResource(
                                        id=azure_utils.get_subnet_id(
                                            subscription_id,
                                            resource_group,
                                            network,
                                            subnet,
                                        )
                                    ),
                                    public_ip_address_configuration=VirtualMachinePublicIPAddressConfiguration(
                                        name="public_ip_config",
                                    ),
                                )
                            ],
                        )
                    ],
                ),
                priority="Spot" if spot else "Regular",
                eviction_policy="Delete" if spot else None,
                identity=VirtualMachineIdentity(
                    type=ResourceIdentityType.USER_ASSIGNED,
                    user_assigned_identities={
                        azure_utils.get_managed_identity_id(
                            subscription_id, resource_group, managed_identity
                        ): UserAssignedIdentitiesValue()
                    },
                ),
                user_data=base64.b64encode(user_data.encode()).decode(),
            ),
        )
    except ResourceExistsError as e:
        # May occur if no quota or quota exceeded
        if e.error.code in ["SkuNotAvailable", "OperationNotAllowed"]:
            raise NoCapacityError()
        raise e
    vm = poller.result()
    return vm


def _get_instance_status(
    compute_client: ComputeManagementClient,
    resource_group: str,
    instance_name: str,
) -> RequestStatus:
    # TODO detect when instance was deleted due to no capacity to support job resubmission
    try:
        vm: VirtualMachine = compute_client.virtual_machines.get(
            resource_group, instance_name, expand="instanceView"
        )
    except ResourceNotFoundError:
        return RequestStatus.TERMINATED

    # https://learn.microsoft.com/en-us/azure/virtual-machines/states-billing
    statuses: List[InstanceViewStatus] = vm.instance_view.statuses
    codes = list(filter(lambda c: c.startswith("PowerState/"), map(attrgetter("code"), statuses)))
    assert len(codes) <= 1

    if not codes:
        return RequestStatus.TERMINATED

    elif len(codes) == 1:
        state = codes[0].split("/")[1]
        # Original documentation uses capitalize words https://learn.microsoft.com/en-us/azure/virtual-machines/states-billing#power-states-and-billing
        if state == "running":
            return RequestStatus.RUNNING
        elif state in {"stopping", "stopped", "deallocating", "deallocated"}:
            return RequestStatus.TERMINATED

    raise RuntimeError(f"unhandled state {codes!r}", codes)


def _terminate_instance(
    compute_client: ComputeManagementClient,
    resource_group: str,
    instance_name: str,
):
    compute_client.virtual_machines.begin_delete(
        resource_group_name=resource_group,
        vm_name=instance_name,
    )
