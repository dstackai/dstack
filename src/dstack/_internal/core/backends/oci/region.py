from functools import cached_property

import oci
from typing_extensions import Any, List, Mapping

from dstack._internal.core.models.backends.oci import AnyOCICreds


class OCIRegion:
    """
    A structure for region-specific objects, including region-bound API clients
    """

    def __init__(self, client_config: Mapping[str, Any]):
        self.client_config = client_config

    @cached_property
    def compute_client(self) -> oci.core.ComputeClient:
        return oci.core.ComputeClient(self.client_config)

    @cached_property
    def identity_client(self) -> oci.identity.IdentityClient:
        return oci.identity.IdentityClient(self.client_config)

    @cached_property
    def availability_domains(self) -> List[oci.identity.models.AvailabilityDomain]:
        return self.identity_client.list_availability_domains(self.client_config["tenancy"]).data


def get_subscribed_region_names(creds: AnyOCICreds) -> List[str]:
    config = creds.to_client_config()
    region = OCIRegion(config)

    subscriptions: List[oci.identity.models.RegionSubscription] = (
        region.identity_client.list_region_subscriptions(config["tenancy"]).data
    )
    return [s.region_name for s in subscriptions if s.status == s.STATUS_READY]
