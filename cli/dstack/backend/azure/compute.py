import base64
import re
from operator import attrgetter
from typing import List, Optional

from azure.core.credentials import TokenCredential
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from azure.mgmt.authorization import AuthorizationManagementClient
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.compute.models import (
    DiskCreateOptionTypes,
    HardwareProfile,
    Image,
    ImageReference,
    InstanceViewStatus,
    ManagedDiskParameters,
    NetworkProfile,
    OSDisk,
    OSProfile,
    ResourceIdentityType,
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
from azure.mgmt.network.models import (
    NetworkSecurityGroup,
    SecurityRule,
    SecurityRuleAccess,
    SecurityRuleDirection,
    SecurityRuleProtocol,
)
from azure.mgmt.resource import ResourceManagementClient

from dstack import version
from dstack.backend.aws.runners import _get_default_ami_image_version, _serialize_runner_yaml
from dstack.backend.azure import runners
from dstack.backend.azure.config import AzureConfig
from dstack.backend.base.compute import Compute, choose_instance_type
from dstack.core.instance import InstanceType
from dstack.core.job import Job
from dstack.core.request import RequestHead, RequestStatus


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
        self._storage_account_id = _get_storage_account_id(
            self.azure_config.subscription_id,
            self.azure_config.resource_group,
            self.azure_config.storage_account,
        )

    def get_instance_type(self, job: Job) -> Optional[InstanceType]:
        instance_types = runners._get_instance_types(
            client=self._compute_client, location=self.azure_config.location
        )
        return choose_instance_type(instance_types=instance_types, requirements=job.requirements)

    def run_instance(self, job: Job, instance_type: InstanceType) -> str:
        network_secutiry_group = _create_network_security_group(
            network_client=self._network_client,
            location=self.azure_config.location,
            resource_group=self.azure_config.resource_group,
        )
        vm = _launch_instance(
            compute_client=self._compute_client,
            subscription_id=self.azure_config.subscription_id,
            location=self.azure_config.location,
            resource_group=self.azure_config.resource_group,
            network_security_group=network_secutiry_group,
            network=self.azure_config.network,
            subnet=self.azure_config.subnet,
            managed_identity=self.azure_config.managed_identity,
            image=_get_image(self._compute_client, len(instance_type.resources.gpus) > 0),
            vm_size=instance_type.instance_name,
            instance_name=_get_instance_name(job),
            user_data=_get_user_data_script(self.azure_config, job, instance_type),
        )
        return vm.name

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

    def cancel_spot_request(self, request_id: str):
        raise NotImplementedError()

    def terminate_instance(self, request_id: str):
        _terminate_instance(
            compute_client=self._compute_client,
            resource_group=self.azure_config.resource_group,
            instance_name=request_id,
        )
        pass
        _terminate_instance(
            compute_client=self._compute_client,
            resource_group=self.azure_config.resource_group,
            instance_name=request_id,
        )
        pass
        _terminate_instance(
            compute_client=self._compute_client,
            resource_group=self.azure_config.resource_group,
            instance_name=request_id,
        )
        pass
        _terminate_instance(
            compute_client=self._compute_client,
            resource_group=self.azure_config.resource_group,
            instance_name=request_id,
        )
        pass
        _terminate_instance(
            compute_client=self._compute_client,
            resource_group=self.azure_config.resource_group,
            instance_name=request_id,
        )
        pass
        _terminate_instance(
            compute_client=self._compute_client,
            resource_group=self.azure_config.resource_group,
            instance_name=request_id,
        )


def _get_storage_account_id(
    subscription_id: str, resource_group: str, storage_account: str
) -> str:
    return f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Storage/storageAccounts/{storage_account}"


def _get_managed_identity_id(
    subscription_id: str, resource_group: str, managed_identity: str
) -> str:
    return f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/{managed_identity}"


def _get_network_security_group_id(
    subscription_id: str, resource_group: str, network_security_group: str
) -> str:
    return f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Network/networkSecurityGroups/{network_security_group}"


def _get_subnet_id(subscription_id: str, resource_group: str, network: str, subnet: str) -> str:
    return f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Network/virtualNetworks/{network}/subnets/{subnet}"


def _get_instance_name(job: Job) -> str:
    # TODO support multiple jobs per run
    return f"dstack-{job.run_name}"


def _get_image_published(
    compute_client: ComputeManagementClient,
    cuda: bool,
    _version: Optional[str] = _get_default_ami_image_version(),
):
    # Check https://dev.to/holger/azure-sdk-for-python-retrieve-vm-image-details-30do
    # compute_client.virtual_machine_images.list
    raise NotImplementedError(
        "Querying for published image is not implemented by missing any image."
    )


def _get_image_stage(
    compute_client: ComputeManagementClient,
    cuda: bool,
    _version: Optional[str] = _get_default_ami_image_version(),
) -> Image:
    pattern_value = []
    pattern_value.append("stgn")
    pattern_value.append("dstack")
    if cuda:
        pattern_value.append(re.escape("cuda-11.1"))
    if _version:
        pattern_value.append(re.escape(_version))
    else:
        pattern_value.append(".*")
    pattern = re.compile(rf"^{re.escape('-').join(pattern_value)}$")
    images = filter(lambda i: pattern.match(i.name), compute_client.images.list())
    # XXX: the idea is to return most recent, but Azure does not have creation date attribute for images.
    recent_images = sorted(images, key=attrgetter("name"), reverse=True)
    if not recent_images:
        raise Exception(f"Can't find an Azure image pattern={pattern.pattern!r}")
    return recent_images[0]


_get_image = _get_image_published
if not version.__is_release__:
    _get_image = _get_image_stage


def _create_network_security_group(
    network_client: NetworkManagementClient,
    location: str,
    resource_group: str,
) -> str:
    security_group_name = "dstackSecurityGroup"
    network_client.network_security_groups.begin_create_or_update(
        resource_group,
        security_group_name,
        NetworkSecurityGroup(
            location=location,
            security_rules=[
                SecurityRule(
                    name="runner_service",
                    protocol=SecurityRuleProtocol.TCP,
                    source_address_prefix="Internet",
                    source_port_range="*",
                    destination_address_prefix="*",
                    destination_port_range="3000-4000",
                    access=SecurityRuleAccess.ALLOW,
                    priority=101,
                    direction=SecurityRuleDirection.INBOUND,
                ),
                SecurityRule(
                    name="runner_ssh",
                    protocol=SecurityRuleProtocol.TCP,
                    source_address_prefix="Internet",
                    source_port_range="*",
                    destination_address_prefix="*",
                    destination_port_range="22",
                    access=SecurityRuleAccess.ALLOW,
                    priority=100,
                    direction=SecurityRuleDirection.INBOUND,
                ),
            ],
        ),
    ).result()
    return security_group_name


def _get_user_data_script(azure_config: AzureConfig, job: Job, instance_type: InstanceType) -> str:
    config_content = azure_config.serialize_yaml().replace("\n", "\\n")
    runner_content = _serialize_runner_yaml(job.runner_id, instance_type.resources, 3000, 4000)
    return f"""#!/bin/sh
mkdir -p /root/.dstack/
echo '{config_content}' > /root/.dstack/config.yaml
echo '{runner_content}' > /root/.dstack/runner.yaml
EXTERNAL_IP=`curl -H "Metadata: true" "http://169.254.169.254/metadata/instance/network/interface/0/ipv4/ipAddress/0/publicIpAddress?api-version=2021-12-13&format=text"`
echo "hostname: $EXTERNAL_IP" >> /root/.dstack/runner.yaml
HOME=/root nohup dstack-runner --log-level 6 start --http-port 4000
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
    image: str,
    vm_size: str,
    instance_name: str,
    user_data: str,
) -> VirtualMachine:
    vm: VirtualMachine = compute_client.virtual_machines.begin_create_or_update(
        resource_group,
        instance_name,
        VirtualMachine(
            location=location,
            hardware_profile=HardwareProfile(vm_size=vm_size),
            storage_profile=StorageProfile(
                image_reference=ImageReference(id=image.id),
                os_disk=OSDisk(
                    create_option=DiskCreateOptionTypes.FROM_IMAGE,
                    managed_disk=ManagedDiskParameters(
                        storage_account_type=StorageAccountTypes.STANDARD_SSD_LRS
                    ),
                    disk_size_gb=100,
                ),
            ),
            os_profile=OSProfile(
                computer_name="computername",
                admin_username="dstack_run",
                admin_password="1234*(&^&*!@Y#HIND)",
            ),
            network_profile=NetworkProfile(
                network_api_version=NetworkManagementClient.DEFAULT_API_VERSION,
                network_interface_configurations=[
                    VirtualMachineNetworkInterfaceConfiguration(
                        name="nic_config",
                        network_security_group=SubResource(
                            id=_get_network_security_group_id(
                                subscription_id,
                                resource_group,
                                network_security_group,
                            )
                        ),
                        ip_configurations=[
                            VirtualMachineNetworkInterfaceIPConfiguration(
                                name="ip_config",
                                subnet=SubResource(
                                    id=_get_subnet_id(
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
            identity=VirtualMachineIdentity(
                type=ResourceIdentityType.USER_ASSIGNED,
                user_assigned_identities={
                    _get_managed_identity_id(
                        subscription_id, resource_group, managed_identity
                    ): UserAssignedIdentitiesValue()
                },
            ),
            user_data=base64.b64encode(user_data.encode()).decode(),
        ),
    ).result()
    return vm


def _get_instance_status(
    compute_client: ComputeManagementClient,
    resource_group: str,
    instance_name: str,
) -> RequestStatus:
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


def _terminate_instance():
    pass


def _terminate_instance(
    compute_client: ComputeManagementClient,
    resource_group: str,
    instance_name: str,
):
    compute_client.virtual_machines.begin_delete(
        resource_group_name=resource_group,
        vm_name=instance_name,
    )


def _terminate_instance():
    pass


def _terminate_instance(
    compute_client: ComputeManagementClient,
    resource_group: str,
    instance_name: str,
):
    compute_client.virtual_machines.begin_delete(
        resource_group_name=resource_group,
        vm_name=instance_name,
    )


def _terminate_instance():
    pass


def _terminate_instance(
    compute_client: ComputeManagementClient,
    resource_group: str,
    instance_name: str,
):
    compute_client.virtual_machines.begin_delete(
        resource_group_name=resource_group,
        vm_name=instance_name,
    )


def _terminate_instance():
    pass


def _terminate_instance(
    compute_client: ComputeManagementClient,
    resource_group: str,
    instance_name: str,
):
    compute_client.virtual_machines.begin_delete(
        resource_group_name=resource_group,
        vm_name=instance_name,
    )


def _terminate_instance():
    pass


def _terminate_instance(
    compute_client: ComputeManagementClient,
    resource_group: str,
    instance_name: str,
):
    compute_client.virtual_machines.begin_delete(
        resource_group_name=resource_group,
        vm_name=instance_name,
    )
