from collections.abc import Iterable
from typing import Dict, List, Optional

from verda import VerdaClient
from verda.exceptions import APIException
from verda.instances import Instance

from dstack._internal.core.backends.base.backend import Compute
from dstack._internal.core.backends.base.compute import (
    ComputeWithAllOffersCached,
    ComputeWithCreateInstanceSupport,
    ComputeWithInstanceVolumesSupport,
    ComputeWithPrivilegedSupport,
    generate_unique_instance_name,
    get_shim_commands,
)
from dstack._internal.core.backends.base.offers import (
    OfferModifier,
    get_catalog_offers,
    get_offers_disk_modifier,
)
from dstack._internal.core.backends.verda.models import VerdaConfig
from dstack._internal.core.errors import BackendError, NoCapacityError, ProvisioningError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel
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

logger = get_logger("verda.compute")

MAX_INSTANCE_NAME_LEN = 60

IMAGE_SIZE = Memory.parse("50GB")

CONFIGURABLE_DISK_SIZE = Range[Memory](min=IMAGE_SIZE, max=None)


class VerdaCompute(
    ComputeWithAllOffersCached,
    ComputeWithCreateInstanceSupport,
    ComputeWithPrivilegedSupport,
    ComputeWithInstanceVolumesSupport,
    Compute,
):
    def __init__(self, config: VerdaConfig, backend_type: BackendType):
        super().__init__()
        self.config = config
        self.client = VerdaClient(
            client_id=self.config.creds.client_id,
            client_secret=self.config.creds.client_secret,
        )
        self.backend_type = backend_type

    def get_all_offers_with_availability(self) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            backend=self.backend_type,
            locations=self.config.regions,
        )
        offers_with_availability = self._get_offers_with_availability(offers)
        return offers_with_availability

    def get_offers_modifiers(self, requirements: Requirements) -> Iterable[OfferModifier]:
        return [get_offers_disk_modifier(CONFIGURABLE_DISK_SIZE, requirements)]

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
        ssh_ids: List[str] = []
        startup_script_id: Optional[str] = None
        try:
            for idx, ssh_public_key in enumerate(public_keys):
                ssh_ids.append(
                    _create_ssh_key(
                        client=self.client,
                        name=f"{instance_name}-{idx}.key",
                        public_key=ssh_public_key,
                    )
                )

            commands = get_shim_commands()
            startup_script = " ".join([" && ".join(commands)])
            script_name = f"{instance_name}.sh"
            startup_script_id = _create_startup_script(
                client=self.client,
                name=script_name,
                script=startup_script,
            )

            disk_size = round(instance_offer.instance.resources.disk.size_mib / 1024)
            image_id = _get_vm_image_id(instance_offer)

            logger.debug(
                "Deploying Verda instance",
                {
                    "instance_type": instance_offer.instance.name,
                    "ssh_key_ids": ssh_ids,
                    "startup_script_id": startup_script_id,
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
                startup_script_id=startup_script_id,
                hostname=instance_name,
                description=instance_name,
                image=image_id,
                disk_size=disk_size,
                is_spot=instance_offer.instance.resources.spot,
                location=instance_offer.region,
            )
        except Exception:
            # startup_script_id and ssh_key_ids are per-instance. Ensure no leaks on failures.
            try:
                _delete_startup_script(self.client, startup_script_id)
            except Exception:
                logger.exception(
                    "Failed to cleanup startup script %s after provisioning failure.",
                    startup_script_id,
                )
            try:
                _delete_ssh_keys(self.client, ssh_ids)
            except Exception:
                logger.exception(
                    "Failed to cleanup ssh keys %s after provisioning failure.",
                    ssh_ids,
                )
            raise
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
            backend_data=VerdaInstanceBackendData(
                startup_script_id=startup_script_id,
                ssh_key_ids=ssh_ids,
            ).json(),
        )

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        backend_data_parsed = VerdaInstanceBackendData.load(backend_data)
        try:
            self.client.instances.action(
                id_list=[instance_id],
                action="delete",
                delete_permanently=True,
            )
        except APIException as e:
            if e.message in [
                "Invalid instance id",
                "Can't discontinue a discontinued instance",
            ]:
                logger.debug("Skipping instance %s termination. Instance not found.", instance_id)
            else:
                raise
        _delete_startup_script(self.client, backend_data_parsed.startup_script_id)
        _delete_ssh_keys(self.client, backend_data_parsed.ssh_key_ids)

    def update_provisioning_data(
        self,
        provisioning_data: JobProvisioningData,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ):
        instance = _get_instance_by_id(self.client, provisioning_data.instance_id)
        if instance is None:
            raise ProvisioningError("Verda instance not found")
        if instance.status not in ("ordered", "provisioning", "running"):
            raise ProvisioningError(f"Unexpected Verda instance status: {instance.status!r}")
        if instance.status == "running":
            provisioning_data.hostname = instance.ip


def _get_vm_image_id(instance_offer: InstanceOfferWithAvailability) -> str:
    # https://api.verda.com/v1/images
    if len(instance_offer.instance.resources.gpus) > 0 and instance_offer.instance.resources.gpus[
        0
    ].name in ["V100", "A6000"]:
        # Ubuntu 22.04 + CUDA 12.0 + Docker
        return "2088da25-bb0d-41cc-a191-dccae45d96fd"
    # Ubuntu 24.04 + CUDA 12.8 Open + Docker
    return "77777777-4f48-4249-82b3-f199fb9b701b"


def _create_ssh_key(client: VerdaClient, name: str, public_key: str) -> str:
    try:
        key = client.ssh_keys.create(name, public_key)
        return key.id
    except APIException as e:
        raise BackendError(f"Verda API error while creating SSH key: {e.message}")


def _create_startup_script(client: VerdaClient, name: str, script: str) -> str:
    try:
        startup_script = client.startup_scripts.create(name, script)
        return startup_script.id
    except APIException as e:
        raise BackendError(f"Verda API error while creating startup script: {e.message}")


def _delete_startup_script(client: VerdaClient, startup_script_id: Optional[str]) -> None:
    if startup_script_id is None:
        return
    try:
        client.startup_scripts.delete_by_id(startup_script_id)
    except APIException as e:
        if _is_startup_script_not_found_error(e):
            logger.debug(
                "Skipping startup script %s deletion. Startup script not found.",
                startup_script_id,
            )
            return
        raise


def _delete_ssh_keys(client: VerdaClient, ssh_key_ids: Optional[List[str]]) -> None:
    if not ssh_key_ids:
        return
    for ssh_key_id in ssh_key_ids:
        _delete_ssh_key(client, ssh_key_id)


def _delete_ssh_key(client: VerdaClient, ssh_key_id: str) -> None:
    try:
        client.ssh_keys.delete_by_id(ssh_key_id)
    except APIException as e:
        if _is_ssh_key_not_found_error(e):
            logger.debug("Skipping ssh key %s deletion. SSH key not found.", ssh_key_id)
            return
        raise


def _is_ssh_key_not_found_error(error: APIException) -> bool:
    code = (error.code or "").lower()
    message = (error.message or "").lower()
    if code == "not_found":
        return True
    if code not in {"", "invalid_request"}:
        return False
    return (
        message == "invalid ssh-key id"
        or message == "invalid ssh key id"
        or message == "not found"
        or ("ssh-key id" in message and "invalid" in message)
        or ("ssh key id" in message and "invalid" in message)
    )


def _is_startup_script_not_found_error(error: APIException) -> bool:
    code = (error.code or "").lower()
    message = (error.message or "").lower()
    if code == "not_found":
        return True
    if code not in {"", "invalid_request"}:
        return False
    return (
        message == "invalid startup script id"
        or message == "invalid script id"
        or message == "not found"
        or ("startup script id" in message and "invalid" in message)
        or ("script id" in message and "invalid" in message)
    )


def _get_instance_by_id(
    client: VerdaClient,
    instance_id: str,
) -> Optional[Instance]:
    try:
        return client.instances.get_by_id(instance_id)
    except APIException as e:
        if e.message == "Invalid instance id":
            return None
        raise


def _deploy_instance(
    client: VerdaClient,
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
            wait_for_status=None,  # return asap
        )
    except APIException as e:
        # FIXME: Catch only no capacity errors
        raise NoCapacityError(f"Verda API error: {e.message}")

    return instance


class VerdaInstanceBackendData(CoreModel):
    startup_script_id: Optional[str] = None
    ssh_key_ids: Optional[List[str]] = None

    @classmethod
    def load(cls, raw: Optional[str]) -> "VerdaInstanceBackendData":
        if raw is None:
            return cls()
        return cls.__response__.parse_raw(raw)
