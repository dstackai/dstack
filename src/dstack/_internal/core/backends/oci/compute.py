from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from dstack._internal.core.backends.base.compute import Compute
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.oci import resources
from dstack._internal.core.backends.oci.auth import get_client_config
from dstack._internal.core.backends.oci.config import OCIConfig
from dstack._internal.core.backends.oci.region import make_region_clients_map
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOffer,
    InstanceOfferWithAvailability,
)
from dstack._internal.core.models.runs import Job, JobProvisioningData, Requirements, Run

SUPPORTED_SHAPE_FAMILIES = [
    "VM.Standard2.",
    "VM.DenseIO1.",
    "VM.DenseIO2.",
    "VM.GPU2.",
    "VM.GPU3.",
    "VM.GPU.A10.",
]


class OCICompute(Compute):
    def __init__(self, config: OCIConfig):
        self.config = config
        # TODO(#1194): use a separate compartment instead of tenancy root
        self.compartment_id = get_client_config(config.creds)["tenancy"]
        self.regions = make_region_clients_map(config.regions, config.creds)

    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            backend=BackendType.OCI,
            locations=self.config.regions,
            requirements=requirements,
            extra_filter=_supported_instances,
        )

        with ThreadPoolExecutor(max_workers=8) as executor:
            shapes_quota = resources.get_shapes_quota(self.regions, self.compartment_id, executor)
            offers_within_quota = [
                offer for offer in offers if offer.instance.name in shapes_quota[offer.region]
            ]
            shapes_availability = resources.get_shapes_availability(
                offers_within_quota, self.regions, self.compartment_id, executor
            )

        offers_with_availability = []
        for offer in offers:
            if offer.instance.name in shapes_availability[offer.region]:
                availability = InstanceAvailability.AVAILABLE
            elif offer.instance.name in shapes_quota[offer.region]:
                availability = InstanceAvailability.NOT_AVAILABLE
            else:
                availability = InstanceAvailability.NO_QUOTA
            offers_with_availability.append(
                InstanceOfferWithAvailability(**offer.dict(), availability=availability)
            )

        return offers_with_availability

    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ) -> JobProvisioningData:
        raise NotImplementedError

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ) -> None:
        raise NotImplementedError


def _supported_instances(offer: InstanceOffer) -> bool:
    if "Flex" in offer.instance.name:
        return False
    return any(map(offer.instance.name.startswith, SUPPORTED_SHAPE_FAMILIES))
