from typing import Any, Dict, List, Optional

from dstack._internal.core.backends.base.compute import (
    Compute,
    ComputeWithAllOffersCached,
    ComputeWithCreateInstanceSupport,
    ComputeWithInstanceVolumesSupport,
    ComputeWithPrivilegedSupport,
    get_shim_commands,
)
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.cloudrift.api_client import RiftClient
from dstack._internal.core.backends.cloudrift.models import CloudRiftConfig
from dstack._internal.core.errors import ComputeError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOffer,
    InstanceOfferWithAvailability,
)
from dstack._internal.core.models.placement import PlacementGroup
from dstack._internal.core.models.runs import JobProvisioningData
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

CLOUDRIFT_VM_SSH_PORT = 22


class CloudRiftCompute(
    ComputeWithAllOffersCached,
    ComputeWithCreateInstanceSupport,
    ComputeWithPrivilegedSupport,
    ComputeWithInstanceVolumesSupport,
    Compute,
):
    def __init__(self, config: CloudRiftConfig):
        super().__init__()
        self.config = config
        self.client = RiftClient(self.config.creds.api_key)

    def get_all_offers_with_availability(
        self, unallocated_resources: bool
    ) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            backend=BackendType.CLOUDRIFT,
            locations=self.config.regions or None,
        )
        offers_with_availabilities = self._get_offers_with_availability(offers)
        return offers_with_availabilities

    def _get_offers_with_availability(
        self, offers: List[InstanceOffer]
    ) -> List[InstanceOfferWithAvailability]:
        instance_types_with_availabilities: List[Dict] = self.client.get_instance_types()

        region_availabilities = {}
        for instance_type in instance_types_with_availabilities:
            for variant in instance_type["variants"]:
                for dc, count in variant["available_nodes_per_dc"].items():
                    if count > 0:
                        key = (variant["name"], dc)
                        region_availabilities[key] = InstanceAvailability.AVAILABLE

        availability_offers = []
        for offer in offers:
            key = (offer.instance.name, offer.region)
            availability = region_availabilities.get(key, InstanceAvailability.NOT_AVAILABLE)
            availability_offers.append(offer.with_availability(availability=availability))

        return availability_offers

    def create_instance(
        self,
        instance_offer: InstanceOfferWithAvailability,
        instance_config: InstanceConfiguration,
        placement_group: Optional[PlacementGroup],
    ) -> JobProvisioningData:
        # TODO: Remove once CloudRift fixes their VM RTC clock.
        # Wrong RTC + NTP backward jump breaks Docker container lifecycle.
        ntp_sync_commands = [
            (
                "timeout 60 bash -c '"
                "while ! timedatectl show -p NTPSynchronized --value | grep -q yes;"
                " do sleep 1; done' || true"
            ),
        ]
        commands = ntp_sync_commands + get_shim_commands()
        startup_script = " ".join([" && ".join(commands)])
        logger.debug(
            f"Creating instance for offer {instance_offer.instance.name} in region {instance_offer.region} with commands: {startup_script}"
        )

        gpu_vendor = None
        if instance_offer.instance.resources.gpus:
            gpu_vendor = instance_offer.instance.resources.gpus[0].vendor.value

        instance_ids = self.client.deploy_instance(
            instance_type=instance_offer.instance.name,
            region=instance_offer.region,
            ssh_keys=instance_config.get_public_keys(),
            cmd=startup_script,
            gpu_vendor=gpu_vendor,
        )

        if len(instance_ids) == 0:
            raise ComputeError(
                f"Failed to create instance for offer {instance_offer.instance.name} in region {instance_offer.region}."
            )

        return JobProvisioningData(
            backend=instance_offer.backend,
            instance_type=instance_offer.instance,
            instance_id=instance_ids[0],
            hostname=None,
            internal_ip=None,
            region=instance_offer.region,
            price=instance_offer.price,
            username="riftuser",
            ssh_port=None,
            dockerized=True,
            ssh_proxy=None,
            backend_data=None,
        )

    def update_provisioning_data(
        self,
        provisioning_data: JobProvisioningData,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ):
        instance_info = self.client.get_instance_by_id(provisioning_data.instance_id)

        if not instance_info:
            return

        instance_mode = instance_info.get("node_mode", "")

        if not instance_mode or instance_mode != "VirtualMachine":
            return

        vms = instance_info.get("virtual_machines", [])
        if len(vms) == 0:
            return

        vm_ready = vms[0].get("ready", False)
        if vm_ready:
            hostname = instance_info.get("host_address", None)
            ssh_port = _get_vm_ssh_port(instance_info)
            if hostname is None or ssh_port is None:
                return
            provisioning_data.hostname = hostname
            provisioning_data.ssh_port = ssh_port

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        terminated = self.client.terminate_instance(instance_id=instance_id)
        if not terminated:
            raise ComputeError(f"Failed to terminate instance {instance_id} in region {region}.")


def _get_vm_ssh_port(instance_info: Dict) -> Optional[int]:
    if ssh_port := _get_vm_ssh_port_from_port_mappings(instance_info):
        return ssh_port
    if ssh_port := _get_vm_ssh_port_from_instructions(instance_info):
        return ssh_port
    if _has_unusable_vm_ssh_port_data(instance_info):
        return None
    return CLOUDRIFT_VM_SSH_PORT


def _get_vm_ssh_port_from_port_mappings(instance_info: Dict) -> Optional[int]:
    port_mappings = instance_info.get("port_mappings")
    if not isinstance(port_mappings, list):
        return None
    for port_mapping in port_mappings:
        parsed_mapping = _parse_port_mapping(port_mapping)
        if parsed_mapping is None:
            continue
        vm_port, host_port = parsed_mapping
        if vm_port == CLOUDRIFT_VM_SSH_PORT:
            return host_port
    return None


def _get_vm_ssh_port_from_instructions(instance_info: Dict) -> Optional[int]:
    instructions = instance_info.get("instructions")
    if not isinstance(instructions, dict):
        return None
    placeholder_values = instructions.get("placeholder_values")
    if not isinstance(placeholder_values, list):
        return None
    for placeholder_value in placeholder_values:
        ssh_port = _parse_ssh_port_placeholder_value(placeholder_value)
        if ssh_port is not None:
            return ssh_port
    return None


def _has_unusable_vm_ssh_port_data(instance_info: Dict) -> bool:
    return isinstance(instance_info.get("port_mappings"), list) or _has_ssh_port_placeholder(
        instance_info
    )


def _has_ssh_port_placeholder(instance_info: Dict) -> bool:
    instructions = instance_info.get("instructions")
    if not isinstance(instructions, dict):
        return False
    placeholder_values = instructions.get("placeholder_values")
    if not isinstance(placeholder_values, list):
        return False
    return any(_is_ssh_port_placeholder_value(value) for value in placeholder_values)


def _parse_ssh_port_placeholder_value(placeholder_value: Any) -> Optional[int]:
    if not _is_ssh_port_placeholder_value(placeholder_value):
        return None
    return _parse_ssh_port_option(placeholder_value[1])


def _is_ssh_port_placeholder_value(placeholder_value: Any) -> bool:
    return (
        isinstance(placeholder_value, (list, tuple))
        and len(placeholder_value) >= 2
        and placeholder_value[0] == "SSH_PORT"
    )


def _parse_ssh_port_option(ssh_port_option: Any) -> Optional[int]:
    if not isinstance(ssh_port_option, str):
        return None
    if ssh_port_option.strip() == "":
        return CLOUDRIFT_VM_SSH_PORT
    parts = ssh_port_option.split()
    if len(parts) != 2 or parts[0] != "-p":
        return None
    return _parse_port(parts[1])


def _parse_port_mapping(port_mapping: Any) -> Optional[tuple[int, int]]:
    if not isinstance(port_mapping, (list, tuple)) or len(port_mapping) < 2:
        return None
    vm_port = _parse_port(port_mapping[0])
    host_port = _parse_port(port_mapping[1])
    if vm_port is None or host_port is None:
        return None
    return vm_port, host_port


def _parse_port(port: Any) -> Optional[int]:
    try:
        parsed_port = int(port)
    except (TypeError, ValueError):
        return None
    if parsed_port <= 0 or parsed_port > 65535:
        return None
    return parsed_port
