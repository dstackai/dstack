import re
import warnings
from typing import Any, List, Optional, Tuple

import google.api_core.exceptions
from google.cloud import compute_v1
from google.oauth2 import service_account

from dstack import version
from dstack.backend.aws.runners import _serialize_runner_yaml
from dstack.backend.base.compute import Compute
from dstack.backend.gcp import utils as gcp_utils
from dstack.backend.gcp.config import GCPConfig
from dstack.core.instance import InstanceType
from dstack.core.job import Job, Requirements
from dstack.core.request import RequestHead, RequestStatus
from dstack.core.runners import Gpu, Resources, Runner

DSTACK_INSTANCE_TAG = "dstack-runner-instance"


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

    def get_request_head(self, job: Job, request_id: Optional[str]) -> RequestHead:
        if request_id is None:
            return RequestHead(
                job_id=job.job_id,
                status=RequestStatus.TERMINATED,
                message="request_id is not specified",
            )
        instance_status = _get_instance_status(
            client=self.instances_client,
            project_id=self.gcp_config.project_id,
            zone=self.gcp_config.zone,
            instance_name=request_id,
        )
        return RequestHead(
            job_id=job.job_id,
            status=instance_status,
            message=None,
        )

    def get_instance_type(self, job: Job) -> Optional[InstanceType]:
        return InstanceType(
            instance_name="n1-standard-1",
            resources=Resources(
                cpus=1, memory_mib=3750, gpus=[], interruptible=False, local=False
            ),
        )

    def run_instance(self, job: Job, instance_type: InstanceType) -> str:
        instance = _launch_instance(
            instances_client=self.instances_client,
            firewalls_client=self.firewalls_client,
            project_id=self.gcp_config.project_id,
            zone=self.gcp_config.zone,
            image_name=_get_image_name(
                images_client=self.images_client,
                instance_type=instance_type,
            ),
            instance_name=_get_instance_name(job),
            user_data_script=_get_user_data_script(self.gcp_config, job, instance_type),
            service_account=self.credentials.service_account_email,
        )
        return instance.name

    def terminate_instance(self, request_id: str):
        _terminate_instance(
            client=self.instances_client,
            gcp_config=self.gcp_config,
            instance_name=request_id,
        )

    def cancel_spot_request(self, request_id: str):
        _terminate_instance(
            client=self.instances_client,
            gcp_config=self.gcp_config,
            instance_name=request_id,
        )


def _get_image_name(
    images_client: compute_v1.ImagesClient, instance_type: InstanceType
) -> Optional[str]:
    if version.__is_release__:
        image_prefix = "dstack-"
    else:
        image_prefix = "stgn-dstack-"
    if len(instance_type.resources.gpus) > 0:
        image_prefix += "cuda-"
    else:
        image_prefix += "nocuda-"
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


def _get_instance_name(job: Job) -> str:
    # TODO support multiple jobs per run
    return f"dstack-{job.run_name}"


def _get_user_data_script(gcp_config: GCPConfig, job: Job, instance_type: InstanceType) -> str:
    config_content = gcp_config.serialize_yaml().replace("\n", "\\n")
    runner_content = _serialize_runner_yaml(job.runner_id, instance_type.resources, 3000, 4000)
    return f"""#!/bin/sh
mkdir -p /root/.dstack/
echo '{config_content}' > /root/.dstack/config.yaml
echo '{runner_content}' > /root/.dstack/runner.yaml
EXTERNAL_IP=`curl -H "Metadata-Flavor: Google" http://169.254.169.254/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip`
echo "hostname: $EXTERNAL_IP" >> /root/.dstack/runner.yaml
HOME=/root nohup dstack-runner --log-level 6 start --http-port 4000
"""


def _launch_instance(
    instances_client: compute_v1.InstancesClient,
    firewalls_client: compute_v1.FirewallsClient,
    project_id: str,
    zone: str,
    image_name: str,
    instance_name: str,
    user_data_script: str,
    service_account: str,
) -> compute_v1.Instance:
    try:
        _create_firewall_rules(firewalls_client=firewalls_client, project_id=project_id)
    except google.api_core.exceptions.Conflict:
        pass
    disk = _disk_from_image(
        disk_type=f"zones/{zone}/diskTypes/pd-balanced",
        disk_size_gb=20,
        boot=True,
        source_image=f"projects/dstack/global/images/{image_name}",
        auto_delete=False,
    )
    instance = _create_instance(
        instances_client=instances_client,
        project_id=project_id,
        zone=zone,
        instance_name=instance_name,
        disks=[disk],
        user_data_script=user_data_script,
        service_account=service_account,
        external_access=True,
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
    machine_type: str = "n1-standard-1",
    network_link: str = "global/networks/default",
    subnetwork_link: str = None,
    internal_ip: str = None,
    external_access: bool = False,
    external_ipv4: str = None,
    accelerators: List[compute_v1.AcceleratorConfig] = None,
    preemptible: bool = False,
    spot: bool = False,
    instance_termination_action: str = "STOP",
    custom_hostname: str = None,
    delete_protection: bool = False,
    user_data_script: Optional[str] = None,
    service_account: Optional[str] = None,
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
        preemptible: boolean value indicating if the new instance should be preemptible
            or not. Preemptible VMs have been deprecated and you should now use Spot VMs.
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
    # Use the network interface provided in the network_link argument.
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

    # Collect information into the Instance object.
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

    if preemptible:
        # Set the preemptible setting
        warnings.warn("Preemptible VMs are being replaced by Spot VMs.", DeprecationWarning)
        instance.scheduling = compute_v1.Scheduling()
        instance.scheduling.preemptible = True

    if spot:
        # Set the Spot VM setting
        instance.scheduling = compute_v1.Scheduling()
        instance.scheduling.provisioning_model = compute_v1.Scheduling.ProvisioningModel.SPOT.name
        instance.scheduling.instance_termination_action = instance_termination_action

    if custom_hostname is not None:
        # Set the custom hostname for the instance
        instance.hostname = custom_hostname

    if delete_protection:
        # Set the delete protection bit
        instance.deletion_protection = True

    if user_data_script is not None:
        instance.metadata = compute_v1.Metadata(
            items=[compute_v1.Items(key="user-data", value=user_data_script)]
        )

    if service_account is not None:
        instance.service_accounts = [
            compute_v1.ServiceAccount(
                email=service_account,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
        ]

    instance.tags = compute_v1.Tags(items=[DSTACK_INSTANCE_TAG])

    # Prepare the request to insert an instance.
    request = compute_v1.InsertInstanceRequest()
    request.zone = zone
    request.project = project_id
    request.instance_resource = instance

    operation = instances_client.insert(request=request)
    gcp_utils.wait_for_extended_operation(operation, "instance creation")

    return instances_client.get(project=project_id, zone=zone, instance=instance_name)


def _create_firewall_rules(
    firewalls_client: compute_v1.FirewallsClient,
    project_id: str,
    network: str = "global/networks/default",
):
    """
    Creates a simple firewall rule allowing for incoming HTTP and HTTPS access from the entire Internet.

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
    firewall_rule.name = "dstack-runner-allow-incoming"
    firewall_rule.direction = "INGRESS"

    allowed_ports_tcp = compute_v1.Allowed()
    allowed_ports_tcp.I_p_protocol = "tcp"
    allowed_ports_tcp.ports = ["3000-4000"]

    allowed_ports_udp = compute_v1.Allowed()
    allowed_ports_udp.I_p_protocol = "udp"
    allowed_ports_udp.ports = ["3000-4000"]

    firewall_rule.allowed = [allowed_ports_tcp, allowed_ports_udp]
    firewall_rule.source_ranges = ["0.0.0.0/0"]
    firewall_rule.network = network
    firewall_rule.description = "Allowing TCP/UDP traffic on ports 3000-4000 from Internet."

    firewall_rule.target_tags = [DSTACK_INSTANCE_TAG]

    operation = firewalls_client.insert(project=project_id, firewall_resource=firewall_rule)
    gcp_utils.wait_for_extended_operation(operation, "firewall rule creation")


def _get_instance_status(
    client: compute_v1.InstancesClient, project_id: str, zone: str, instance_name: str
) -> RequestStatus:
    get_instance_request = compute_v1.GetInstanceRequest(
        instance=instance_name,
        project=project_id,
        zone=zone,
    )
    try:
        instance = client.get(get_instance_request)
    except google.api_core.exceptions.NotFound:
        return RequestStatus.TERMINATED
    if instance.status in ["PROVISIONING", "STAGING", "RUNNING"]:
        return RequestStatus.RUNNING
    return RequestStatus.TERMINATED


def _terminate_instance(
    client: compute_v1.InstancesClient, gcp_config: GCPConfig, instance_name: str
):
    _delete_instance(
        client=client,
        instance_name=instance_name,
        project_id=gcp_config.project_id,
        zone=gcp_config.zone,
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
