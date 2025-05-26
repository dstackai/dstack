import concurrent.futures
import re
from typing import Dict, List, Optional, Tuple

import google.api_core.exceptions
import google.cloud.compute_v1 as compute_v1
from google.api_core.extended_operation import ExtendedOperation
from google.api_core.operation import Operation
from google.cloud import tpu_v2

from dstack._internal.core.errors import BackendError, ComputeError
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


def get_availability_zones(
    regions_client: compute_v1.RegionsClient,
    project_id: str,
    region: str,
) -> List[str]:
    region_info = regions_client.get(project=project_id, region=region)
    return [full_resource_name_to_name(z) for z in region_info.zones]


def check_vpc(
    subnetworks_client: compute_v1.SubnetworksClient,
    routers_client: compute_v1.RoutersClient,
    project_id: str,
    regions: List[str],
    allocate_public_ip: bool,
    vpc_name: Optional[str] = None,
    shared_vpc_project_id: Optional[str] = None,
    nat_check: bool = True,
):
    if vpc_name is None:
        vpc_name = "default"
    vpc_project_id = project_id
    if shared_vpc_project_id:
        vpc_project_id = shared_vpc_project_id
    try:
        usable_subnets = list_project_usable_subnets(
            subnetworks_client=subnetworks_client, project_id=vpc_project_id
        )
        for region in regions:
            get_vpc_subnet_or_error(
                subnetworks_client=subnetworks_client,
                vpc_project_id=vpc_project_id,
                vpc_name=vpc_name,
                region=region,
                usable_subnets=usable_subnets,
            )
    except google.api_core.exceptions.NotFound:
        raise ComputeError(f"Failed to find VPC project {vpc_project_id}")

    if allocate_public_ip:
        return

    # We may have no permissions to check NAT in a shared VPC
    if nat_check and shared_vpc_project_id is None:
        regions_without_nat = []
        for region in regions:
            if not has_vpc_nat_access(routers_client, vpc_project_id, vpc_name, region):
                regions_without_nat.append(region)

        if regions_without_nat:
            raise ComputeError(
                f"VPC {vpc_name} in project {vpc_project_id} does not have Cloud NAT configured"
                f" for outbound internet connectivity in regions: {regions_without_nat}."
                " Specify `nat_check: false` if you use a different mechanism"
                " for outbound internet connectivity such as a third-party NAT appliance."
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
    extra_subnetworks: Optional[List[Tuple[str, str]]] = None,
    allocate_public_ip: bool = True,
    placement_policy: Optional[str] = None,
) -> compute_v1.Instance:
    instance = compute_v1.Instance()
    instance.name = instance_name
    instance.machine_type = f"zones/{zone}/machineTypes/{machine_type}"
    instance.network_interfaces = _get_network_interfaces(
        network=network,
        subnetwork=subnetwork,
        allocate_public_ip=allocate_public_ip,
        extra_subnetworks=extra_subnetworks,
    )

    disk = compute_v1.AttachedDisk()
    disk.auto_delete = True
    disk.boot = True
    initialize_params = compute_v1.AttachedDiskInitializeParams()
    initialize_params.source_image = image_id
    initialize_params.disk_size_gb = disk_size
    if instance_type_supports_persistent_disk(machine_type):
        initialize_params.disk_type = f"zones/{zone}/diskTypes/pd-balanced"
    else:
        initialize_params.disk_type = f"zones/{zone}/diskTypes/hyperdisk-balanced"
    disk.initialize_params = initialize_params
    instance.disks = [disk]

    if accelerators:
        instance.guest_accelerators = accelerators

    if (
        accelerators
        or machine_type.startswith("a3-")
        or machine_type.startswith("a2-")
        or machine_type.startswith("g2-")
    ):
        # Attachable GPUs, H100, A100, and L4
        instance.scheduling.on_host_maintenance = "TERMINATE"

    if placement_policy is not None:
        instance.resource_policies = [placement_policy]

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


def _get_network_interfaces(
    network: str,
    subnetwork: Optional[str],
    allocate_public_ip: bool,
    extra_subnetworks: Optional[List[Tuple[str, str]]],
) -> List[compute_v1.NetworkInterface]:
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

    if extra_subnetworks:
        # Multiple interfaces are set only for GPU VM that require gVNIC for best performance
        network_interface.nic_type = compute_v1.NetworkInterface.NicType.GVNIC.name

    network_interfaces = [network_interface]
    for network, subnetwork in extra_subnetworks or []:
        network_interfaces.append(
            compute_v1.NetworkInterface(
                network=network,
                subnetwork=subnetwork,
                nic_type=compute_v1.NetworkInterface.NicType.GVNIC.name,
            )
        )
    return network_interfaces


def list_project_usable_subnets(
    subnetworks_client: compute_v1.SubnetworksClient,
    project_id: str,
) -> List[compute_v1.UsableSubnetwork]:
    request = compute_v1.ListUsableSubnetworksRequest(project=project_id)
    return [s for s in subnetworks_client.list_usable(request=request)]


def get_vpc_subnet_or_error(
    subnetworks_client: compute_v1.SubnetworksClient,
    vpc_project_id: str,
    vpc_name: str,
    region: str,
    usable_subnets: Optional[List[compute_v1.UsableSubnetwork]] = None,
) -> str:
    """
    Returns resource name of any usable subnet in a given VPC
    (e.g. "projects/example-project/regions/europe-west4/subnetworks/example-subnet")
    """
    if usable_subnets is None:
        usable_subnets = list_project_usable_subnets(subnetworks_client, vpc_project_id)
    for subnet in usable_subnets:
        network_name = subnet.network.split("/")[-1]
        subnet_url = subnet.subnetwork
        subnet_resource_name = remove_prefix(subnet_url, "https://www.googleapis.com/compute/v1/")
        subnet_region = subnet_resource_name.split("/")[3]
        if network_name == vpc_name and subnet_region == region:
            return subnet_resource_name
    raise ComputeError(
        f"No usable subnetwork found in region {region} for VPC {vpc_name} in project {vpc_project_id}."
        f" Ensure that VPC {vpc_name} exists and has usable subnetworks."
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
    if len(gpus) == 0 or gpus[0].name in {"H100", "A100", "L4"}:
        # H100, A100, and L4 are bundled with the instance
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


def filter_invalid_labels(labels: Dict[str, str]) -> Dict[str, str]:
    filtered_labels = {}
    for k, v in labels.items():
        if not _is_valid_label(k, v):
            logger.warning("Skipping invalid label '%s: %s'", k, v)
            continue
        filtered_labels[k] = v
    return filtered_labels


def validate_labels(labels: Dict[str, str]):
    for k, v in labels.items():
        if not _is_valid_label(k, v):
            raise BackendError(
                "Invalid resource labels. "
                "See labels restrictions: https://cloud.google.com/compute/docs/labeling-resources#requirements"
            )


def _is_valid_label(key: str, value: str) -> bool:
    return is_valid_resource_name(key) and is_valid_label_value(value)


MAX_RESOURCE_NAME_LEN = 63
NAME_PATTERN = re.compile(r"^[a-z][_\-a-z0-9]{0,62}$")
LABEL_VALUE_PATTERN = re.compile(r"^[_\-a-z0-9]{0,63}$")


def is_valid_resource_name(name: str) -> bool:
    if len(name) < 1 or len(name) > MAX_RESOURCE_NAME_LEN:
        return False
    match = re.match(NAME_PATTERN, name)
    return match is not None


def is_valid_label_value(value: str) -> bool:
    match = re.match(LABEL_VALUE_PATTERN, value)
    return match is not None


def create_tpu_node_struct(
    instance_name: str,
    startup_script: str,
    authorized_keys: List[str],
    spot: bool,
    labels: Dict[str, str],
    runtime_version: str = "tpu-ubuntu2204-base",
    network: str = "global/networks/default",
    subnetwork: Optional[str] = None,
    allocate_public_ip: bool = True,
    service_account: Optional[str] = None,
    data_disks: Optional[List[tpu_v2.AttachedDisk]] = None,
) -> tpu_v2.Node:
    node = tpu_v2.Node()
    if spot:
        node.scheduling_config = tpu_v2.SchedulingConfig(preemptible=True)
    node.accelerator_type = instance_name
    node.runtime_version = runtime_version
    node.network_config = tpu_v2.NetworkConfig(
        enable_external_ips=allocate_public_ip,
        network=network,
        subnetwork=subnetwork,
    )
    ssh_keys = "\n".join(f"ubuntu:{key}" for key in authorized_keys)
    node.metadata = {"ssh-keys": ssh_keys, "startup-script": startup_script}
    node.labels = labels
    if service_account is not None:
        node.service_account = tpu_v2.ServiceAccount(
            email=service_account,
            scope=["https://www.googleapis.com/auth/cloud-platform"],
        )
    if data_disks is not None:
        for disk in data_disks:
            node.data_disks.append(disk)
    return node


def wait_for_extended_operation(
    operation: ExtendedOperation, verbose_name: str = "operation", timeout: int = 300
):
    result = operation.result(timeout=timeout)

    if operation.error_code:
        # Write only debug logs here.
        # The unexpected errors will be propagated and logged appropriately by the caller.
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
        # The unexpected errors will be propagated and logged appropriately by the caller.
        logger.debug("Error during %s: %s", verbose_name, e)
        raise operation.exception() or e
    return result


def full_resource_name_to_name(full_resource_name: str) -> str:
    return full_resource_name.split("/")[-1]


def vpc_name_to_vpc_resource_name(project_id: str, vpc_name: str) -> str:
    return f"projects/{project_id}/global/networks/{vpc_name}"


def get_placement_policy_resource_name(
    project_id: str,
    region: str,
    placement_policy: str,
) -> str:
    return f"projects/{project_id}/regions/{region}/resourcePolicies/{placement_policy}"


def instance_type_supports_persistent_disk(instance_type_name: str) -> bool:
    return not any(
        instance_type_name.startswith(series)
        for series in [
            "m4-",
            "c4-",
            "n4-",
            "h3-",
            "v6e",
        ]
    )
