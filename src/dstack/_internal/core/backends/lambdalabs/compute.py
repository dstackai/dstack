from typing import List, Optional

from dstack._internal.core.backends.base.compute import Compute
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.lambdalabs.api_client import LambdaAPIClient
from dstack._internal.core.backends.lambdalabs.config import LambdaConfig
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOffer,
    InstanceOfferWithAvailability,
    InstanceState,
    LaunchedInstanceInfo,
)
from dstack._internal.core.models.runs import Job, Requirements, Run


class LambdaCompute(Compute):
    def __init__(self, config: LambdaConfig):
        self.config = config
        self.api_client = LambdaAPIClient(config.creds.api_key)

    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            provider="lambdalabs",
            locations=self.config.regions,
            requirements=requirements,
        )
        offers_with_availability = self._get_offers_with_availability(offers)
        return offers_with_availability

    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
    ) -> LaunchedInstanceInfo:
        # TODO: implement once Lambda has capacity for testing
        raise NotImplementedError()

    def terminate_instance(self, instance_id: str, region: str):
        self.api_client.terminate_instances(instance_ids=[instance_id])

    def _get_offers_with_availability(
        self, offers: List[InstanceOffer]
    ) -> List[InstanceOfferWithAvailability]:
        instance_availability = {
            instance_name: [
                region["name"] for region in details["regions_with_capacity_available"]
            ]
            for instance_name, details in self.api_client.list_instance_types().items()
        }
        availability_offers = []
        for offer in offers:
            if offer.region not in self.config.regions:
                continue
            availability = InstanceAvailability.NOT_AVAILABLE
            if offer.region in instance_availability.get(offer.instance.name, []):
                availability = InstanceAvailability.AVAILABLE
            availability_offers.append(
                InstanceOfferWithAvailability(**offer.dict(), availability=availability)
            )
        return availability_offers
