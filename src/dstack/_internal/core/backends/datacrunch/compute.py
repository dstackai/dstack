from typing import Dict, List, Optional

from datacrunch import DataCrunchClient
from datacrunch.exceptions import APIException
from datacrunch.instances.instances import Instance

from dstack._internal.core.backends.base.backend import Compute
from dstack._internal.core.backends.base.compute import (
    ComputeWithCreateInstanceSupport,
    generate_unique_instance_name,
    get_shim_commands,
)
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.datacrunch.models import DataCrunchConfig
from dstack._internal.core.errors import NoCapacityError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOffer,
    InstanceOfferWithAvailability,
)
from dstack._internal.core.models.placement import PlacementGroup
from dstack._internal.core.models.resources import Memory, Range
from dstack._internal.core.models.runs import JobProvisioningData, Requirements
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.ssh import get_public_key_fingerprint

logger = get_logger("datacrunch.compute")

MAX_INSTANCE_NAME_LEN = 60

IMAGE_SIZE = Memory.parse("50GB")

CONFIGURABLE_DISK_SIZE = Range[Memory](min=IMAGE_SIZE, max=None)


class DataCrunchCompute(
    ComputeWithCreateInstanceSupport,
    Compute,
):
    def __init__(self, config: DataCrunchConfig):
        super().__init__()
        self.config = config
        self.client = DataCrunchClient(
            client_id=self.config.creds.client_id,
            client_secret=self.config.creds.client_secret,
        )

    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            backend=BackendType.DATACRUNCH,
            locations=self.config.regions,
            requirements=requirements,
            configurable_disk_size=CONFIGURABLE_DISK_SIZE,
        )
        offers_with_availability = self._get_offers_with_availability(offers)
        return offers_with_availability

    def _get_offers_with_availability(
        self, offers: List[InstanceOffer]
    ) -> List[InstanceOfferWithAvailability]:
        raw_availabilities: List[Dict] = self.client.instances.get_availabilities()

        region_availabilities = {}
        for location in raw_availabilities:
            location_code = location["location_code"]
            availabilities = location["availabilities"]
            for name in availabilities:
                key = (name, location_code)
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
        instance_name = generate_unique_instance_name(
            instance_config, max_length=MAX_INSTANCE_NAME_LEN
        )
        public_keys = instance_config.get_public_keys()
        ssh_ids = []
        for ssh_public_key in public_keys:
            ssh_ids.append(
                # datacrunch allows you to use the same name
                _get_or_create_ssh_key(
                    client=self.client,
                    name=f"dstack-{instance_config.instance_name}.key",
                    public_key=ssh_public_key,
                )
            )

        commands = get_shim_commands(authorized_keys=public_keys)
        startup_script = " ".join([" && ".join(commands)])
        script_name = f"dstack-{instance_config.instance_name}.sh"
        startup_script_ids = _get_or_create_startup_scrpit(
            client=self.client,
            name=script_name,
            script=startup_script,
        )

        disk_size = round(instance_offer.instance.resources.disk.size_mib / 1024)
        image_id = _get_vm_image_id(instance_offer)

        logger.debug(
            "Deploying datacrunch instance",
            {
                "instance_type": instance_offer.instance.name,
                "ssh_key_ids": ssh_ids,
                "startup_script_id": startup_script_ids,
                "hostname": instance_name,
                "description": instance_name,
                "image": image_id,
                "disk_size": disk_size,
                "location": instance_offer.region,
            },
        )
        instance = _deploy_instance(
            client=self.client,
            instance_type=instance_offer.instance.name,
            ssh_key_ids=ssh_ids,
            startup_script_id=startup_script_ids,
            hostname=instance_name,
            description=instance_name,
            image=image_id,
            disk_size=disk_size,
            is_spot=instance_offer.instance.resources.spot,
            location=instance_offer.region,
        )
        return JobProvisioningData(
            backend=instance_offer.backend,
            instance_type=instance_offer.instance,
            instance_id=instance.id,
            hostname=None,
            internal_ip=None,
            region=instance.location,
            price=instance_offer.price,
            username="root",
            ssh_port=22,
            dockerized=True,
            ssh_proxy=None,
            backend_data=None,
        )

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        try:
            self.client.instances.action(id_list=[instance_id], action="delete")
        except APIException as e:
            if e.message in [
                "Invalid instance id",
                "Can't discontinue a discontinued instance",
            ]:
                logger.debug("Skipping instance %s termination. Instance not found.", instance_id)
                return
            raise

    def update_provisioning_data(
        self,
        provisioning_data: JobProvisioningData,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ):
        instance = _get_instance_by_id(self.client, provisioning_data.instance_id)
        if instance is not None and instance.status == "running":
            provisioning_data.hostname = instance.ip


def _get_vm_image_id(instance_offer: InstanceOfferWithAvailability) -> str:
    # https://api.datacrunch.io/v1/images
    if (
        len(instance_offer.instance.resources.gpus) > 0
        and instance_offer.instance.resources.gpus[0].name == "V100"
    ):
        # Ubuntu 22.04 + CUDA 12.0 + Docker
        return "2088da25-bb0d-41cc-a191-dccae45d96fd"
    # Ubuntu 24.04 + CUDA 12.8 Open + Docker
    return "77777777-4f48-4249-82b3-f199fb9b701b"


def _get_or_create_ssh_key(client: DataCrunchClient, name: str, public_key: str) -> str:
    fingerprint = get_public_key_fingerprint(public_key)
    keys = client.ssh_keys.get()
    found_keys = [key for key in keys if fingerprint == get_public_key_fingerprint(key.public_key)]
    if found_keys:
        key = found_keys[0]
        return key.id
    key = client.ssh_keys.create(name, public_key)
    return key.id


def _get_or_create_startup_scrpit(client: DataCrunchClient, name: str, script: str) -> str:
    scripts = client.startup_scripts.get()
    found_scripts = [startup_script for startup_script in scripts if script == startup_script]
    if found_scripts:
        startup_script = found_scripts[0]
        return startup_script.id

    startup_script = client.startup_scripts.create(name, script)
    return startup_script.id


def _get_instance_by_id(
    client: DataCrunchClient,
    instance_id: str,
) -> Optional[Instance]:
    try:
        return client.instances.get_by_id(instance_id)
    except APIException as e:
        if e.message == "Invalid instance id":
            return None
        raise


def _deploy_instance(
    client: DataCrunchClient,
    instance_type: str,
    image: str,
    ssh_key_ids: List[str],
    hostname: str,
    description: str,
    startup_script_id: str,
    disk_size: int,
    is_spot: bool,
    location: str,
) -> Instance:
    try:
        instance = client.instances.create(
            instance_type=instance_type,
            image=image,
            ssh_key_ids=ssh_key_ids,
            hostname=hostname,
            description=description,
            startup_script_id=startup_script_id,
            pricing="FIXED_PRICE",
            is_spot=is_spot,
            location=location,
            os_volume={"name": "OS volume", "size": disk_size},
        )
    except APIException as e:
        # FIXME: Catch only no capacity errors
        raise NoCapacityError(f"DataCrunch API error: {e.message}")

    return instance
