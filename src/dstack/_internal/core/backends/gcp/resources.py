import concurrent.futures
import random
import re
import string
from typing import Dict, List, Optional

import google.api_core.exceptions
import google.cloud.compute_v1 as compute_v1
from google.api_core.extended_operation import ExtendedOperation
from google.api_core.operation import Operation
from google.cloud import tpu_v2

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
    routers_client: compute_v1.RoutersClient,
    project_id: str,
    regions: List[str],
    allocate_public_ip: bool,
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

    if allocate_public_ip:
        return

    regions_without_nat = []
    for region in regions:
        if not has_vpc_nat_access(routers_client, vpc_project_id, vpc_name, region):
            regions_without_nat.append(region)

    if regions_without_nat:
        raise ComputeError(
            f"VPC {vpc_name} in project {vpc_project_id} does not have Cloud NAT configured for external internet access in regions: {regions_without_nat}"
        )


def has_vpc_nat_access(
    routers_client: compute_v1.RoutersClient,
    project_id: str,
    vpc_name: str,
    region: str,
) -> bool:
    try:
        routers = routers_client.list(project=project_id, region=region)
    except google.api_core.exceptions.NotFound:
        return False

    for router in routers:
        if router.network.endswith(vpc_name):
            if len(router.nats) > 0:
                return True

    return False


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
    allocate_public_ip: bool = True,
) -> compute_v1.Instance:
    network_interface = compute_v1.NetworkInterface()
    network_interface.network = network
    if subnetwork is not None:
        network_interface.subnetwork = subnetwork

    if allocate_public_ip:
        access = compute_v1.AccessConfig()
        access.type_ = compute_v1.AccessConfig.Type.ONE_TO_ONE_NAT.name
        access.name = "External NAT"
        access.network_tier = access.NetworkTier.PREMIUM.name
        network_interface.access_configs = [access]
    else:
        network_interface.access_configs = []

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
    allowed_ports.ports = ["22", "80", "443"]

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


def create_tpu_node_struct(
    instance_name: str,
    startup_script: str,
    authorized_keys: List[str],
    spot: bool,
    labels: Dict[str, str],
    subnetwork: Optional[str] = None,
    allocate_public_ip: bool = True,
) -> tpu_v2.Node:
    node = tpu_v2.Node()
    if spot:
        node.scheduling_config = tpu_v2.SchedulingConfig(preemptible=True)
    node.accelerator_type = instance_name
    node.runtime_version = "tpu-ubuntu2204-base"
    # subnetwork determines the network, so network shouldn't be specified
    node.network_config = tpu_v2.NetworkConfig(
        enable_external_ips=allocate_public_ip,
        subnetwork=subnetwork,
    )
    ssh_keys = "\n".join(f"ubuntu:{key}" for key in authorized_keys)
    node.metadata = {"ssh-keys": ssh_keys, "startup-script": startup_script}
    node.labels = labels
    return node


def wait_for_extended_operation(
    operation: ExtendedOperation, verbose_name: str = "operation", timeout: int = 300
):
    result = operation.result(timeout=timeout)

    if operation.error_code:
        # Write only debug logs here.
        # The unexpected errors will be propagated and logged appropriatly by the caller.
        logger.debug(
            "Error during %s: [Code: %s]: %s",
            verbose_name,
            operation.error_code,
            operation.error_message,
        )
        logger.debug("Operation ID: %s", operation.name)
        raise operation.exception() or RuntimeError(operation.error_message)

    return result


def wait_for_operation(operation: Operation, verbose_name: str = "operation", timeout: int = 300):
    try:
        result = operation.result(timeout=timeout)
    except concurrent.futures.TimeoutError as e:
        logger.debug("Error during %s: %s", verbose_name, e)
        raise
    except Exception as e:
        # Write only debug logs here.
        # The unexpected errors will be propagated and logged appropriatly by the caller.
        logger.debug("Error during %s: %s", verbose_name, e)
        raise operation.exception() or e
    return result
