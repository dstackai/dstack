import base64
from typing import List, Optional

from azure.core.credentials import TokenCredential
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.mgmt import compute as compute_mgmt
from azure.mgmt import network as network_mgmt
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

from dstack import version
from dstack._internal.core.backends.azure import utils as azure_utils
from dstack._internal.core.backends.azure.config import AzureConfig
from dstack._internal.core.backends.base.compute import Compute, get_user_data
from dstack._internal.core.errors import NoCapacityError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceOfferWithAvailability,
    InstanceState,
    LaunchedInstanceInfo,
)
from dstack._internal.core.models.runs import Job, Requirements, Run
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class AzureCompute(Compute):
    def __init__(self, config: AzureConfig, credential: TokenCredential):
        self.config = config
        self.credential = credential
        self._compute_client = compute_mgmt.ComputeManagementClient(
            credential=credential, subscription_id=self.azure_config.subscription_id
        )
        self._network_client = network_mgmt.NetworkManagementClient(
            credential=credential, subscription_id=self.azure_config.subscription_id
        )

    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        pass

    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
    ) -> LaunchedInstanceInfo:
        location = instance_offer.region
        logger.info(
            "Requesting %s %s instance in %s...",
            instance_offer.instance.name,
            "spot" if instance_offer.instance.resources.spot else "",
            location,
        )
        try:
            vm = _launch_instance(
                compute_client=self._compute_client,
                subscription_id=self.config.subscription_id,
                location=location,
                resource_group=self.config.resource_group,
                network_security_group=azure_utils.get_default_network_security_group_name(
                    resource_group=self.config.resource_group,
                    location=location,
                ),
                network=azure_utils.get_default_network_name(
                    resource_group=self.config.resource_group,
                    location=location,
                ),
                subnet=azure_utils.get_default_subnet_name(
                    resource_group=self.config.resource_group,
                    location=location,
                ),
                managed_identity=azure_utils.get_runner_managed_identity_name(
                    resource_group=self.config.resource_group
                ),
                image_reference=_get_image_ref(
                    compute_client=self._compute_client,
                    location=location,
                    cuda=len(instance_offer.instance.resources.gpus) > 0,
                ),
                vm_size=instance_offer.instance.name,
                instance_name=job.job_spec.job_name,
                user_data=get_user_data(
                    backend=BackendType.AZURE,
                    image_name=job.job_spec.image_name,
                    authorized_keys=[
                        run.run_spec.ssh_key_pub.strip(),
                        project_ssh_public_key.strip(),
                    ],
                ),
                ssh_pub_key=job.ssh_key_pub,
                spot=instance_offer.instance.resources.spot,
            )
            logger.info("Request succeeded")
            public_ip = _get_vm_public_ip(
                network_client=self._network_client,
                resource_group=self.config.resource_group,
                vm=vm,
            )
            return LaunchedInstanceInfo(
                instance_id=vm.name,
                ip_address=public_ip,
                region=location,
                username="ubuntu",
                ssh_port=22,
                dockerized=True,
            )
        except NoCapacityError:
            logger.info("Failed to request instance in %s", location)
        logger.info("Failed to request instance")
        raise NoCapacityError()

    def terminate_instance(self, instance_id: str, region: str):
        pass


def _get_image_ref(
    compute_client: compute_mgmt.ComputeManagementClient,
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


def _launch_instance(
    compute_client: compute_mgmt.ComputeManagementClient,
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
                    network_api_version=network_mgmt.NetworkManagementClient.DEFAULT_API_VERSION,
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


def _get_vm_public_ip(
    network_client: network_mgmt.NetworkManagementClient,
    resource_group: str,
    vm: VirtualMachine,
) -> str:
    nic_id = vm.network_profile.network_interfaces[0]
    nic_name = azure_utils.get_resource_name_from_resource_id(nic_id)
    nic = network_client.network_interfaces.get(resource_group, nic_name)
    return nic.ip_configurations[0].public_ip_address.ip_address
