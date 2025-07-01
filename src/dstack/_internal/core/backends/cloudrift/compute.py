from typing import Dict, List, Optional

from dstack._internal.core.backends.base.backend import Compute
from dstack._internal.core.backends.base.compute import (
    ComputeWithCreateInstanceSupport,
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
from dstack._internal.core.models.runs import JobProvisioningData, Requirements
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class CloudRiftCompute(
    ComputeWithCreateInstanceSupport,
    Compute,
):
    def __init__(self, config: CloudRiftConfig):
        super().__init__()
        self.config = config
        self.client = RiftClient(self.config.creds.api_key)

    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            backend=BackendType.CLOUDRIFT,
            locations=self.config.regions or None,
            requirements=requirements,
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
            availability_offers.append(
                InstanceOfferWithAvailability(**offer.dict(), availability=availability)
            )

        return availability_offers

    def create_instance(
        self,
        instance_offer: InstanceOfferWithAvailability,
        instance_config: InstanceConfiguration,
        placement_group: Optional[PlacementGroup],
    ) -> JobProvisioningData:
        commands = get_shim_commands(authorized_keys=instance_config.get_public_keys())
        startup_script = " ".join([" && ".join(commands)])
        logger.debug(
            f"Creating instance for offer {instance_offer.instance.name} in region {instance_offer.region} with commands: {startup_script}"
        )

        instance_ids = self.client.deploy_instance(
            instance_type=instance_offer.instance.name,
            region=instance_offer.region,
            ssh_keys=instance_config.get_public_keys(),
            cmd=startup_script,
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
            ssh_port=22,
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
            provisioning_data.hostname = instance_info.get("host_address", None)

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        terminated = self.client.terminate_instance(instance_id=instance_id)
        if not terminated:
            raise ComputeError(f"Failed to terminate instance {instance_id} in region {region}.")
