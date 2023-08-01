from typing import Dict, List

import google.api_core.exceptions
from google.cloud import compute_v1

import dstack._internal.backend.gcp.utils as gcp_utils

DSTACK_GATEWAY_TAG = "dstack-gateway"


def create_gateway_instance(
    instances_client: compute_v1.InstancesClient,
    firewalls_client: compute_v1.FirewallsClient,
    project_id: str,
    network: str,
    subnet: str,
    zone: str,
    instance_name: str,
    service_account: str,
    labels: Dict[str, str],
    ssh_key_pub: str,
    machine_type: str = "e2-micro",
) -> compute_v1.Instance:
    try:
        create_gateway_firewall_rules(
            firewalls_client=firewalls_client,
            project_id=project_id,
            network=network,
        )
    except google.api_core.exceptions.Conflict:
        pass

    network_interface = compute_v1.NetworkInterface()
    network_interface.name = network
    network_interface.subnetwork = subnet

    access = compute_v1.AccessConfig()
    access.type_ = compute_v1.AccessConfig.Type.ONE_TO_ONE_NAT.name
    access.name = "External NAT"
    access.network_tier = access.NetworkTier.PREMIUM.name
    network_interface.access_configs = [access]

    instance = compute_v1.Instance()
    instance.network_interfaces = [network_interface]
    instance.name = instance_name
    instance.disks = gateway_disks(zone)
    instance.machine_type = f"zones/{zone}/machineTypes/{machine_type}"

    metadata_items = [
        compute_v1.Items(key="ssh-keys", value=f"ubuntu:{ssh_key_pub}"),
        compute_v1.Items(key="user-data", value=gateway_user_data_script()),
    ]
    instance.metadata = compute_v1.Metadata(items=metadata_items)
    instance.labels = labels
    instance.tags = compute_v1.Tags(items=[DSTACK_GATEWAY_TAG])  # to apply firewall rules

    instance.service_accounts = [
        compute_v1.ServiceAccount(
            email=service_account,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
    ]

    request = compute_v1.InsertInstanceRequest()
    request.zone = zone
    request.project = project_id
    request.instance_resource = instance
    operation = instances_client.insert(request=request)
    gcp_utils.wait_for_extended_operation(operation, "instance creation")

    return instances_client.get(project=project_id, zone=zone, instance=instance_name)


def create_gateway_firewall_rules(
    firewalls_client: compute_v1.FirewallsClient,
    project_id: str,
    network: str,
):
    firewall_rule = compute_v1.Firewall()
    firewall_rule.name = "dstack-gateway-in-all-" + network.replace("/", "-")
    firewall_rule.direction = "INGRESS"

    allowed_ports = compute_v1.Allowed()
    allowed_ports.I_p_protocol = "tcp"
    allowed_ports.ports = ["0-65535"]

    firewall_rule.allowed = [allowed_ports]
    firewall_rule.source_ranges = ["0.0.0.0/0"]
    firewall_rule.network = network
    firewall_rule.description = "Allowing TCP traffic on all ports from Internet."

    firewall_rule.target_tags = [DSTACK_GATEWAY_TAG]

    operation = firewalls_client.insert(project=project_id, firewall_resource=firewall_rule)
    gcp_utils.wait_for_extended_operation(operation, "firewall rule creation")


def gateway_disks(zone: str) -> List[compute_v1.AttachedDisk]:
    disk = compute_v1.AttachedDisk()

    initialize_params = compute_v1.AttachedDiskInitializeParams()
    initialize_params.source_image = (
        "projects/ubuntu-os-cloud/global/images/ubuntu-2204-jammy-v20230714"
    )
    initialize_params.disk_size_gb = 10
    initialize_params.disk_type = f"zones/{zone}/diskTypes/pd-balanced"

    disk.initialize_params = initialize_params
    disk.auto_delete = True
    disk.boot = True
    return [disk]


def gateway_user_data_script() -> str:
    return f"""#!/bin/sh
sudo apt-get update
DEBIAN_FRONTEND=noninteractive sudo apt-get install -y -q nginx
WWW_UID=$(id -u www-data)
WWW_GID=$(id -g www-data)
install -m 700 -o $WWW_UID -g $WWW_GID -d /var/www/.ssh
install -m 600 -o $WWW_UID -g $WWW_GID /dev/null /var/www/.ssh/authorized_keys"""
