import random
import re
import string
from typing import Dict, List, Optional

import google.api_core.exceptions
import google.cloud.compute_v1 as compute_v1
from google.api_core.extended_operation import ExtendedOperation

import dstack.version as version
from dstack._internal.core.errors import ComputeError
from dstack._internal.core.models.instances import Gpu
from dstack._internal.utils.common import remove_prefix
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

DSTACK_INSTANCE_TAG = "dstack-runner-instance"
DSTACK_GATEWAY_TAG = "dstack-gateway-instance"

supported_accelerators = [
    {"accelerator_name": "nvidia-a100-80gb", "gpu_name": "A100", "memory_mb": 1024 * 80},
    {"accelerator_name": "nvidia-tesla-a100", "gpu_name": "A100", "memory_mb": 1024 * 40},
    {"accelerator_name": "nvidia-l4", "gpu_name": "L4", "memory_mb": 1024 * 24},
    {"accelerator_name": "nvidia-tesla-t4", "gpu_name": "T4", "memory_mb": 1024 * 16},
    {"accelerator_name": "nvidia-tesla-v100", "gpu_name": "V100", "memory_mb": 1024 * 16},
    {"accelerator_name": "nvidia-tesla-p100", "gpu_name": "P100", "memory_mb": 1024 * 16},
]


def check_vpc(
    network_client: compute_v1.NetworksClient,
    project_id: str,
    vpc_name: Optional[str] = None,
    shared_vpc_project_id: Optional[str] = None,
):
    if vpc_name is None:
        vpc_name = "default"
    vpc_project_id = project_id
    if shared_vpc_project_id:
        vpc_project_id = shared_vpc_project_id
    try:
        network_client.get(project=vpc_project_id, network=vpc_name)
    except google.api_core.exceptions.NotFound:
        raise ComputeError(f"Failed to find VPC {vpc_name} in project {vpc_project_id}")


def create_instance_struct(
    disk_size: int,
    image_id: str,
    machine_type: str,
    accelerators: List[compute_v1.AcceleratorConfig],
    spot: bool,
    user_data: str,
    authorized_keys: List[str],
    labels: Dict[str, str],
    tags: List[str],
    instance_name: str,
    zone: str,
    service_account: Optional[str] = None,
    network: str = "global/networks/default",
    subnetwork: Optional[str] = None,
) -> compute_v1.Instance:
    network_interface = compute_v1.NetworkInterface()
    network_interface.network = network
    if subnetwork is not None:
        network_interface.subnetwork = subnetwork
    access = compute_v1.AccessConfig()
    access.type_ = compute_v1.AccessConfig.Type.ONE_TO_ONE_NAT.name
    access.name = "External NAT"
    access.network_tier = access.NetworkTier.PREMIUM.name
    network_interface.access_configs = [access]

    instance = compute_v1.Instance()
    instance.network_interfaces = [network_interface]
    instance.name = instance_name
    instance.machine_type = f"zones/{zone}/machineTypes/{machine_type}"

    disk = compute_v1.AttachedDisk()
    disk.auto_delete = True
    disk.boot = True
    initialize_params = compute_v1.AttachedDiskInitializeParams()
    initialize_params.source_image = image_id
    initialize_params.disk_size_gb = disk_size
    initialize_params.disk_type = f"zones/{zone}/diskTypes/pd-balanced"
    disk.initialize_params = initialize_params
    instance.disks = [disk]

    if accelerators:
        instance.guest_accelerators = accelerators

    if accelerators or machine_type.startswith("a2-") or machine_type.startswith("g2-"):
        # Attachable GPUs, A100, and L4
        instance.scheduling.on_host_maintenance = "TERMINATE"

    if spot:
        instance.scheduling = compute_v1.Scheduling()
        instance.scheduling.provisioning_model = compute_v1.Scheduling.ProvisioningModel.SPOT.name
        instance.scheduling.instance_termination_action = "STOP"  # TODO?

    metadata_items = [
        compute_v1.Items(key="user-data", value=user_data),
        compute_v1.Items(
            key="ssh-keys", value="\n".join(f"ubuntu:{key}" for key in authorized_keys)
        ),
    ]
    instance.metadata = compute_v1.Metadata(items=metadata_items)

    instance.labels = labels
    instance.tags = compute_v1.Tags(items=tags)

    if service_account is not None:
        instance.service_accounts = [
            compute_v1.ServiceAccount(
                email=service_account,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
        ]

    return instance


def get_image_id(cuda: bool) -> str:
    if not cuda:
        image_name = f"dstack-{version.base_image}"
    else:
        image_name = f"dstack-cuda-{version.base_image}"
    image_name = image_name.replace(".", "-")

    return f"projects/dstack/global/images/{image_name}"


def get_gateway_image_id() -> str:
    return "projects/ubuntu-os-cloud/global/images/ubuntu-2204-jammy-v20230714"


def get_vpc_subnet_or_error(
    subnetworks_client: compute_v1.SubnetworksClient,
    vpc_project_id: str,
    vpc_name: str,
    region: str,
) -> str:
    """
    Returns resource name of any usable subnet in a given VPC
    (e.g. "projects/example-project/regions/europe-west4/subnetworks/example-subnet")
    """
    request = compute_v1.ListUsableSubnetworksRequest(project=vpc_project_id)
    for subnet in subnetworks_client.list_usable(request=request):
        network_name = subnet.network.split("/")[-1]
        subnet_url = subnet.subnetwork
        subnet_resource_name = remove_prefix(subnet_url, "https://www.googleapis.com/compute/v1/")
        subnet_region = subnet_resource_name.split("/")[3]
        if network_name == vpc_name and subnet_region == region:
            return subnet_resource_name
    raise ComputeError(
        f"No usable subnetwork found in region {region} for VPC {vpc_name} in project {vpc_project_id}"
    )


def create_runner_firewall_rules(
    firewalls_client: compute_v1.FirewallsClient,
    project_id: str,
    network: str = "global/networks/default",
):
    network_name = network.split("/")[-1]
    firewall_rule_name = "dstack-ssh-in-" + network.replace("/", "-")
    if not is_valid_resource_name(firewall_rule_name):
        firewall_rule_name = "dstack-ssh-in-" + network_name
    firewall_rule = compute_v1.Firewall()
    firewall_rule.name = firewall_rule_name
    firewall_rule.direction = "INGRESS"

    allowed_ssh_port = compute_v1.Allowed()
    allowed_ssh_port.I_p_protocol = "tcp"
    allowed_ssh_port.ports = ["22"]

    firewall_rule.allowed = [allowed_ssh_port]
    firewall_rule.source_ranges = ["0.0.0.0/0"]
    firewall_rule.network = network
    firewall_rule.description = "Allowing only SSH connections from Internet."

    firewall_rule.target_tags = [DSTACK_INSTANCE_TAG]

    try:
        operation = firewalls_client.insert(project=project_id, firewall_resource=firewall_rule)
        wait_for_extended_operation(operation, "firewall rule creation")
    except google.api_core.exceptions.Conflict:
        pass


def create_gateway_firewall_rules(
    firewalls_client: compute_v1.FirewallsClient,
    project_id: str,
    network: str = "global/networks/default",
):
    network_name = network.split("/")[-1]
    firewall_rule_name = "dstack-gateway-in-all-" + network.replace("/", "-")
    if not is_valid_resource_name(firewall_rule_name):
        firewall_rule_name = "dstack-gateway-in-all-" + network_name
    firewall_rule = compute_v1.Firewall()
    firewall_rule.name = firewall_rule_name
    firewall_rule.direction = "INGRESS"

    allowed_ports = compute_v1.Allowed()
    allowed_ports.I_p_protocol = "tcp"
    allowed_ports.ports = ["0-65535"]

    firewall_rule.allowed = [allowed_ports]
    firewall_rule.source_ranges = ["0.0.0.0/0"]
    firewall_rule.network = network
    firewall_rule.description = "Allowing TCP traffic on all ports from Internet."

    firewall_rule.target_tags = [DSTACK_GATEWAY_TAG]

    try:
        operation = firewalls_client.insert(project=project_id, firewall_resource=firewall_rule)
        wait_for_extended_operation(operation, "firewall rule creation")
    except google.api_core.exceptions.Conflict:
        pass


def get_accelerators(
    project_id: str, zone: str, gpus: List[Gpu]
) -> List[compute_v1.AcceleratorConfig]:
    if len(gpus) == 0 or gpus[0].name in {"A100", "L4"}:
        # A100 and L4 are bundled with the instance
        return []
    accelerator_config = compute_v1.AcceleratorConfig()
    accelerator_config.accelerator_count = len(gpus)
    for acc in supported_accelerators:
        if gpus[0].name == acc["gpu_name"] and gpus[0].memory_mib == acc["memory_mb"]:
            accelerator_name = acc["accelerator_name"]
            break
    else:
        raise ValueError(f"Unsupported GPU: {gpus[0].name} {gpus[0].memory_mib} MiB")
    accelerator_config.accelerator_type = (
        f"projects/{project_id}/zones/{zone}/acceleratorTypes/{accelerator_name}"
    )
    return [accelerator_config]


def wait_for_extended_operation(
    operation: ExtendedOperation, verbose_name: str = "operation", timeout: int = 300
):
    result = operation.result(timeout=timeout)

    if operation.error_code:
        logger.error(
            "Error during %s: [Code: %s]: %s",
            verbose_name,
            operation.error_code,
            operation.error_message,
        )
        logger.error("Operation ID: %s", operation.name)
        raise operation.exception() or RuntimeError(operation.error_message)

    return result


NAME_PATTERN = re.compile(r"^[a-z]([-a-z0-9]*[a-z0-9])?$")

LABEL_VALUE_PATTERN = re.compile(r"^[-a-z0-9]{0,63}$")


def is_valid_resource_name(name: str) -> bool:
    if len(name) < 1 or len(name) > 63:
        return False
    match = re.match(NAME_PATTERN, name)
    return match is not None


def is_valid_label_value(value: str) -> bool:
    match = re.match(LABEL_VALUE_PATTERN, value)
    return match is not None


def generate_random_resource_name(length: int = 40) -> str:
    return random.choice(string.ascii_lowercase) + "".join(
        random.choice(string.ascii_lowercase + string.digits) for _ in range(length)
    )
