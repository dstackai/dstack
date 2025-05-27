from typing import Dict, List, Optional, Union

import requests

from dstack._internal.core.backends.base.backend import Compute
from dstack._internal.core.backends.base.compute import (
    ComputeWithCreateInstanceSupport,
)
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.cloudrift.models import CloudRiftConfig
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOffer,
    InstanceOfferWithAvailability,
)
from dstack._internal.core.models.runs import Job, JobProvisioningData, Requirements, Run
from dstack._internal.core.models.volumes import Volume
from dstack._internal.utils.logging import get_logger
from src.dstack._internal.core.backends.cloudrift.models import CloudRiftAPIKeyCreds

logger = get_logger(__name__)


CLOUDRIFT_SERVER_ADDRESS = "https://api.cloudrift.ai"
CLOUDRIFT_API_VERSION = "2025-03-21"


class CloudRiftCompute(
    ComputeWithCreateInstanceSupport,
    Compute,
):
    def __init__(self, config: CloudRiftConfig):
        super().__init__()
        self.config = config

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
        instance_types_with_availabilities: List[Dict] = _get_instance_types()

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
    ) -> JobProvisioningData:
        # TODO: Implement if backend supports creating instances (VM-based).
        # Delete if backend can only run jobs (container-based).
        raise NotImplementedError()

    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
        volumes: List[Volume],
    ) -> JobProvisioningData:
        # TODO: Implement if create_instance() is not implemented. Delete otherwise.
        raise NotImplementedError()

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        raise NotImplementedError()


def _get_instance_types():
    request_data = {"selector": {"ByServiceAndLocation": {"services": ["vm"]}}}
    response_data = _make_request("instance-types/list", request_data)
    return response_data["instance_types"]


def _make_request(endpoint: str, request_data: dict) -> Union[dict, str, None]:
    response = requests.request(
        "POST",
        f"{CLOUDRIFT_SERVER_ADDRESS}/api/v1/{endpoint}",
        json={"version": CLOUDRIFT_API_VERSION, "data": request_data},
        timeout=5.0,
    )
    if not response.ok:
        response.raise_for_status()
    try:
        response_json = response.json()
        if isinstance(response_json, str):
            return response_json
        return response_json["data"]
    except requests.exceptions.JSONDecodeError:
        return None


if __name__ == "__main__":
    compute = CloudRiftCompute(CloudRiftConfig(creds=CloudRiftAPIKeyCreds(api_key="asdasdasd")))
    print(compute.get_offers())
