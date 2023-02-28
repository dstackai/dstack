import random
import re
import string
from operator import attrgetter
from shlex import quote
from typing import Optional

from azure.core.credentials import TokenCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.compute.v2022_11_01.models import (
    DiskCreateOptionTypes,
    HardwareProfile,
    Image,
    ImageReference,
    ManagedDiskParameters,
    NetworkInterfaceReference,
    NetworkProfile,
    OSDisk,
    OSProfile,
    RunCommandInput,
    RunCommandInputParameter,
    RunCommandResult,
    StorageAccountTypes,
    StorageProfile,
    VirtualMachine,
)
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.network.v2022_07_01.models import (
    AddressSpace,
    IPAllocationMethod,
    NetworkInterface,
    NetworkInterfaceIPConfiguration,
    NetworkSecurityGroup,
    PublicIPAddress,
    PublicIPAddressSku,
    PublicIPAddressSkuName,
    SecurityRule,
    SecurityRuleAccess,
    SecurityRuleDirection,
    SecurityRuleProtocol,
    Subnet,
    VirtualNetwork,
)
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.resource.resources.v2022_09_01.models import ResourceGroup

from dstack import version
from dstack.backend.aws.runners import _get_default_ami_image_version, _serialize_runner_yaml
from dstack.backend.azure import runners
from dstack.backend.base.compute import Compute
from dstack.core.instance import InstanceType
from dstack.core.job import Job
from dstack.core.repo import RepoAddress
from dstack.core.request import RequestHead


class AzureCompute(Compute):
    def __init__(self, credential: TokenCredential, subscription_id: str, location: str):
        self._compute_client = ComputeManagementClient(
            credential=credential, subscription_id=subscription_id
        )
        self._resource_client = ResourceManagementClient(
            credential=credential, subscription_id=subscription_id
        )
        self._network_client = NetworkManagementClient(
            credential=credential, subscription_id=subscription_id
        )
        self._location = location

    def cancel_spot_request(self, request_id: str):
        raise NotImplementedError

    def terminate_instance(self, request_id: str):
        raise NotImplementedError

    def get_instance_type(self, job: Job) -> Optional[InstanceType]:
        instance_types = runners._get_instance_types(
            client=self._compute_client, location=self._location
        )
        instance_types.sort(key=runners._key_for_instance)
        return runners._get_instance_type(
            instance_types=instance_types, requirements=job.requirements
        )

    def run_instance(self, job: Job, instance_type: InstanceType) -> str:
        return _launch_instance(
            self._compute_client,
            self._resource_client,
            self._network_client,
            self._location,
            instance_type,
            job.runner_id,
            job.repo_address,
        )

    def get_request_head(self, job: Job, request_id: Optional[str]) -> RequestHead:
        raise NotImplementedError


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


group_name_patter = re.compile(r"[-\w\._\(\)]+")


def make_name(value: str) -> str:
    value = "".join(group_name_patter.findall(value))
    if value[-1] == ".":
        value = value[:-1]
    return value


def _launch_instance(
    compute_client: ComputeManagementClient,
    resource_client: ResourceManagementClient,
    network_client: NetworkManagementClient,
    location: str,
    instance_type: InstanceType,
    runner_id: str,
    repo_address: RepoAddress,
) -> str:
    image = _get_image(compute_client, len(instance_type.resources.gpus) > 0)

    # Group is shared across runs. Other resources are allocated for particular run.
    # https://learn.microsoft.com/en-us/rest/api/resources/resource-groups/create-or-update?tabs=HTTP#uri-parameters
    # The name of the resource group to create or update.
    # Can include
    # alphanumeric,
    # underscore,
    # parentheses,
    # hyphen,
    # period (except at end),
    # and Unicode characters that match the allowed characters.
    # ^[-\w\._\(\)]+$
    salt = "".join(random.choice(string.ascii_lowercase) for _ in range(5))
    group_name = make_name(f"dstack-{repo_address.repo_name}-{runner_id}-{salt}")

    # XXX: Hardcode for seed up development
    group_name = "dstack-hardcode"
    if not resource_client.resource_groups.check_existence(group_name):
        resource_client.resource_groups.create_or_update(
            group_name,
            ResourceGroup(location=location),
        )

    # XXX: Azure tires to document restriction for name of different resource's kinds. Assume reusing of group name rules.
    # https://learn.microsoft.com/en-us/rest/api/virtualnetwork/virtual-networks/create-or-update?tabs=HTTP#uri-parameters
    if "network_name" not in set(
        map(attrgetter("name"), network_client.virtual_networks.list(group_name))
    ):
        network_client.virtual_networks.begin_create_or_update(
            group_name,
            "network_name",
            VirtualNetwork(
                location=location, address_space=AddressSpace(address_prefixes=["10.0.0.0/16"])
            ),
        ).result()

    if "subnet_name" not in set(
        map(attrgetter("name"), network_client.subnets.list(group_name, "network_name"))
    ):
        subnet = network_client.subnets.begin_create_or_update(
            group_name, "network_name", "subnet_name", Subnet(address_prefix="10.0.0.0/24")
        ).result()
    else:
        subnet = network_client.subnets.get(group_name, "network_name", "subnet_name")

    if "public_ip_address_name" not in set(
        map(
            attrgetter("name"),
            network_client.public_ip_addresses.list(
                group_name,
            ),
        )
    ):
        ip_address: PublicIPAddress = network_client.public_ip_addresses.begin_create_or_update(
            group_name,
            "public_ip_address_name",
            PublicIPAddress(
                location=location,
                sku=PublicIPAddressSku(name=PublicIPAddressSkuName.STANDARD),
                public_ip_allocation_method=IPAllocationMethod.STATIC,
            ),
        ).result()
    else:
        ip_address = network_client.public_ip_addresses.get(
            group_name,
            "public_ip_address_name",
        )

    if "network_security_group_name" not in set(
        map(
            attrgetter("name"),
            network_client.network_security_groups.list(
                group_name,
            ),
        )
    ):
        network_security_group: NetworkSecurityGroup = (
            network_client.network_security_groups.begin_create_or_update(
                group_name,
                "network_security_group_name",
                NetworkSecurityGroup(
                    location=location,
                    security_rules=[
                        SecurityRule(
                            name="security_rule",
                            protocol=SecurityRuleProtocol.TCP,
                            source_address_prefix="Internet",
                            source_port_range="*",
                            destination_address_prefix="*",
                            destination_port_range="22",
                            access=SecurityRuleAccess.ALLOW,
                            priority=100,
                            direction=SecurityRuleDirection.INBOUND,
                        )
                    ],
                ),
            ).result()
        )
    else:
        network_security_group = network_client.network_security_groups.get(
            group_name,
            "network_security_group_name",
        )

    if "interface_name" not in set(
        map(
            attrgetter("name"),
            network_client.network_interfaces.list(
                group_name,
            ),
        )
    ):
        nic_result: NetworkInterface = network_client.network_interfaces.begin_create_or_update(
            group_name,
            "interface_name",
            NetworkInterface(
                location=location,
                network_security_group=NetworkSecurityGroup(id=network_security_group.id),
                ip_configurations=[
                    NetworkInterfaceIPConfiguration(
                        name="DstackIpConfig",
                        subnet=Subnet(id=subnet.id),
                        public_ip_address=PublicIPAddress(id=ip_address.id),
                    )
                ],
            ),
        ).result()
    else:
        nic_result = network_client.network_interfaces.get(
            group_name,
            "interface_name",
        )

    # The supplied password must be between 6-72 characters long and must satisfy at least 3 of password complexity requirements from the following:
    # 1) Contains an uppercase character
    # 2) Contains a lowercase character
    # 3) Contains a numeric digit
    # 4) Contains a special character
    # 5) Control characters are not allowed
    password = "".join(
        "".join(
            map(
                random.choice,
                (
                    string.ascii_uppercase,
                    string.ascii_lowercase,
                    string.digits,
                    string.punctuation,
                ),
            )
        )
        for _ in range(4)
    )
    if "virtual_machine_name" not in set(
        map(
            attrgetter("name"),
            compute_client.virtual_machines.list(
                group_name,
            ),
        )
    ):
        from pathlib import Path

        with (Path().resolve() / "vm.txt").open("w") as stream:
            stream.writelines([f"dstack_run@{ip_address.ip_address}\n", password])
        vm: VirtualMachine = compute_client.virtual_machines.begin_create_or_update(
            group_name,
            "virtual_machine_name",
            VirtualMachine(
                location=location,
                hardware_profile=HardwareProfile(
                    vm_size=instance_type.instance_name,
                ),
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
                    admin_password=password,
                ),
                network_profile=NetworkProfile(
                    network_interfaces=[
                        NetworkInterfaceReference(
                            id=nic_result.id,
                        )
                    ]
                ),
            ),
        ).result()
    else:
        vm = compute_client.virtual_machines.get(
            group_name,
            "virtual_machine_name",
        )

    port_range_from: int = 3000
    port_range_to: int = 4000
    sysctl_port_range_from = int((port_range_to - port_range_from) / 2) + port_range_from
    sysctl_port_range_to = port_range_to - 1
    runner_port_range_from = port_range_from
    runner_port_range_to = sysctl_port_range_from - 1

    result: RunCommandResult = compute_client.virtual_machines.begin_run_command(
        group_name,
        vm.name,
        parameters=RunCommandInput(
            command_id="RunShellScript",
            script=[
                "sudo -s",
                'sysctl -w net.ipv4.ip_local_port_range="${SYSCTL_PORT_RANGE_FROM} ${SYSCTL_PORT_RANGE_TO}"',
                "mkdir /root/.dstack/",
                'echo "$DSTACK_CONFIG" > /root/.dstack/config.yaml',
                'echo "$RUNNER_HEAD_CONFIG" > /root/.dstack/runner.yaml',
                'echo "hostname: $PUBLIC_IP" >> /root/.dstack/runner.yaml',
                "HOME=/root nohup dstack-runner start --http-port 4000 &",
            ],
            parameters=[
                RunCommandInputParameter(name="PUBLIC_IP", value=quote(ip_address.ip_address)),
                RunCommandInputParameter(
                    name="SYSCTL_PORT_RANGE_FROM", value=quote(str(sysctl_port_range_from))
                ),
                RunCommandInputParameter(
                    name="SYSCTL_PORT_RANGE_TO", value=quote(str(sysctl_port_range_to))
                ),
                RunCommandInputParameter(
                    name="RUNNER_HEAD_CONFIG",
                    value=quote(
                        _serialize_runner_yaml(
                            runner_id,
                            instance_type.resources,
                            runner_port_range_from,
                            runner_port_range_to,
                        )
                    ),
                ),
                RunCommandInputParameter(name="DSTACK_CONFIG", value=quote("backend: azure\\n")),
            ],
        ),
    ).result()

    print(result.as_dict())

    return group_name
