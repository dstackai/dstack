import base64
from typing import List

from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.compute.models import (
    DiskCreateOptionTypes,
    HardwareProfile,
    ImageReference,
    LinuxConfiguration,
    ManagedDiskParameters,
    NetworkProfile,
    OSDisk,
    OSProfile,
    SshConfiguration,
    SshPublicKey,
    StorageAccountTypes,
    StorageProfile,
    SubResource,
    VirtualMachine,
    VirtualMachineNetworkInterfaceConfiguration,
    VirtualMachineNetworkInterfaceIPConfiguration,
    VirtualMachinePublicIPAddressConfiguration,
)
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.network.models import (
    NetworkInterface,
    NetworkInterfaceIPConfiguration,
    NetworkSecurityGroup,
    PublicIPAddress,
    SecurityRule,
    SecurityRuleAccess,
    SecurityRuleDirection,
    SecurityRuleProtocol,
)

import dstack._internal.backend.azure.utils as azure_utils


def create_gateway(
    compute_client: ComputeManagementClient,
    network_client: NetworkManagementClient,
    subscription_id: str,
    location: str,
    resource_group: str,
    network: str,
    subnet: str,
    instance_name: str,
    ssh_key_pub: str,
    vm_size: str = "Standard_B1s",
) -> VirtualMachine:
    poller = compute_client.virtual_machines.begin_create_or_update(
        resource_group,
        instance_name,
        VirtualMachine(
            location=location,
            hardware_profile=HardwareProfile(vm_size=vm_size),
            storage_profile=gateway_storage_profile(),
            os_profile=OSProfile(
                computer_name="gatewayvm",
                admin_username="ubuntu",
                linux_configuration=LinuxConfiguration(
                    ssh=SshConfiguration(
                        public_keys=[
                            SshPublicKey(
                                path="/home/ubuntu/.ssh/authorized_keys",
                                key_data=ssh_key_pub,
                            )
                        ]
                    )
                ),
            ),
            network_profile=NetworkProfile(
                network_api_version=NetworkManagementClient.DEFAULT_API_VERSION,
                network_interface_configurations=gateway_interface_configurations(
                    network_client=network_client,
                    subscription_id=subscription_id,
                    location=location,
                    resource_group=resource_group,
                    network=network,
                    subnet=subnet,
                ),
            ),
            priority="Regular",
            user_data=base64.b64encode(gateway_user_data_script().encode()).decode(),
            tags={
                "owner": "dstack",
                "role": "gateway",
            },
        ),
    )
    vm = poller.result()
    return vm


def gateway_storage_profile() -> StorageProfile:
    return StorageProfile(
        image_reference=ImageReference(
            publisher="canonical",
            offer="0001-com-ubuntu-server-jammy",
            sku="22_04-lts",
            version="latest",
        ),
        os_disk=OSDisk(
            create_option=DiskCreateOptionTypes.FROM_IMAGE,
            managed_disk=ManagedDiskParameters(
                storage_account_type=StorageAccountTypes.STANDARD_SSD_LRS
            ),
            disk_size_gb=30,
            delete_option="Delete",
        ),
    )


def gateway_interface_configurations(
    network_client: NetworkManagementClient,
    subscription_id: str,
    location: str,
    resource_group: str,
    network: str,
    subnet: str,
) -> List[VirtualMachineNetworkInterfaceConfiguration]:
    conf = VirtualMachineNetworkInterfaceConfiguration(
        name="nic_config",
        network_security_group=SubResource(
            id=gateway_network_security_group(network_client, location, resource_group)
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
    return [conf]


def gateway_network_security_group(
    network_client: NetworkManagementClient,
    location: str,
    resource_group: str,
) -> str:
    poller = network_client.network_security_groups.begin_create_or_update(
        resource_group_name=resource_group,
        network_security_group_name="dstack-gateway-network-security-group",
        parameters=NetworkSecurityGroup(
            location=location,
            security_rules=[
                SecurityRule(
                    name="runner_service",
                    protocol=SecurityRuleProtocol.TCP,
                    source_address_prefix="Internet",
                    source_port_range="*",
                    destination_address_prefix="*",
                    destination_port_range="0-65535",
                    access=SecurityRuleAccess.ALLOW,
                    priority=101,
                    direction=SecurityRuleDirection.INBOUND,
                )
            ],
        ),
    )
    security_group: NetworkSecurityGroup = poller.result()
    return security_group.id


def get_network_interface(
    network_client: NetworkManagementClient, resource_group: str, interface: str
) -> NetworkInterface:
    return network_client.network_interfaces.get(resource_group, interface)


def get_public_ip(
    network_client: NetworkManagementClient, resource_group: str, public_ip: str
) -> PublicIPAddress:
    return network_client.public_ip_addresses.get(resource_group, public_ip)


def gateway_user_data_script() -> str:
    return f"""#!/bin/sh
sudo apt-get update
DEBIAN_FRONTEND=noninteractive sudo apt-get install -y -q nginx
WWW_UID=$(id -u www-data)
WWW_GID=$(id -g www-data)
install -m 700 -o $WWW_UID -g $WWW_GID -d /var/www/.ssh
install -m 600 -o $WWW_UID -g $WWW_GID /dev/null /var/www/.ssh/authorized_keys"""
