from dataclasses import dataclass
from functools import cached_property
from typing import Any, Dict, Iterable, List, Mapping, Set

import oci

from dstack._internal.core.backends.oci.auth import get_client_config
from dstack._internal.core.models.backends.oci import AnyOCICreds


class OCIRegionClient:
    """
    A structure for region-specific objects, including region-bound API clients
    """

    def __init__(self, client_config: Mapping[str, Any]):
        self.client_config = client_config

    @property
    def name(self) -> str:
        return self.client_config["region"]

    @cached_property
    def compute_client(self) -> oci.core.ComputeClient:
        return oci.core.ComputeClient(self.client_config)

    @cached_property
    def identity_client(self) -> oci.identity.IdentityClient:
        return oci.identity.IdentityClient(self.client_config)

    @cached_property
    def marketplace_client(self) -> oci.marketplace.MarketplaceClient:
        return oci.marketplace.MarketplaceClient(self.client_config)

    @cached_property
    def object_storage_client(self) -> oci.object_storage.ObjectStorageClient:
        return oci.object_storage.ObjectStorageClient(self.client_config)

    @cached_property
    def virtual_network_client(self) -> oci.core.VirtualNetworkClient:
        return oci.core.VirtualNetworkClient(self.client_config)

    @cached_property
    def work_request_client(self) -> oci.work_requests.WorkRequestClient:
        return oci.work_requests.WorkRequestClient(self.client_config)

    @cached_property
    def availability_domains(self) -> List[oci.identity.models.AvailabilityDomain]:
        return self.identity_client.list_availability_domains(self.client_config["tenancy"]).data


def make_region_client(region_name: str, creds: AnyOCICreds) -> OCIRegionClient:
    config = dict(get_client_config(creds))
    config["region"] = region_name
    return OCIRegionClient(config)


def make_region_clients_map(
    region_names: Iterable[str], creds: AnyOCICreds
) -> Dict[str, OCIRegionClient]:
    config = get_client_config(creds)
    result = {}
    for region_name in region_names:
        region_config = dict(config)
        region_config["region"] = region_name
        result[region_name] = OCIRegionClient(region_config)
    return result


@dataclass
class SubscribedRegions:
    names: Set[str]
    home_region_name: str


def get_subscribed_regions(creds: AnyOCICreds) -> SubscribedRegions:
    config = get_client_config(creds)
    region = OCIRegionClient(config)

    subscriptions: List[oci.identity.models.RegionSubscription] = (
        region.identity_client.list_region_subscriptions(config["tenancy"]).data
    )
    names = {s.region_name for s in subscriptions if s.status == s.STATUS_READY}
    home_region_name = next(s.region_name for s in subscriptions if s.is_home_region)

    return SubscribedRegions(names=names, home_region_name=home_region_name)
