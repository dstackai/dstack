import re
from typing import Dict, List

from azure.mgmt import network as network_mgmt
from azure.mgmt.network.models import Subnet

from dstack._internal.core.errors import BackendError
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


MAX_RESOURCE_NAME_LEN = 64


def get_network_subnets(
    network_client: network_mgmt.NetworkManagementClient,
    resource_group: str,
    network_name: str,
    private: bool,
) -> List[str]:
    res = []
    subnets = network_client.subnets.list(
        resource_group_name=resource_group, virtual_network_name=network_name
    )
    for subnet in subnets:
        if private:
            if _is_eligible_private_subnet(
                network_client=network_client,
                resource_group=resource_group,
                network_name=network_name,
                subnet=subnet,
            ):
                res.append(subnet.name)
        else:
            if _is_eligible_public_subnet(
                network_client=network_client,
                resource_group=resource_group,
                network_name=network_name,
                subnet=subnet,
            ):
                res.append(subnet.name)
    return res


def _is_eligible_public_subnet(
    network_client: network_mgmt.NetworkManagementClient,
    resource_group: str,
    network_name: str,
    subnet: Subnet,
) -> bool:
    # Apparently, in Azure practically any subnet can be used
    # to provision instances with public IPs
    return True


def _is_eligible_private_subnet(
    network_client: network_mgmt.NetworkManagementClient,
    resource_group: str,
    network_name: str,
    subnet: Subnet,
) -> bool:
    # Azure provides default outbound connectivity but it's deprecated
    # and does not work with Flexible orchestration used in dstack,
    # so we require an explicit outbound method such as NAT Gateway.

    if subnet.nat_gateway is not None:
        return True

    vnet_peerings = list(
        network_client.virtual_network_peerings.list(
            resource_group_name=resource_group,
            virtual_network_name=network_name,
        )
    )
    if len(vnet_peerings) > 0:
        # We currently assume that any peering can provide outbound connectivity.
        # There can be a more elaborate check of the peering configuration.
        return True

    return False


def filter_invalid_tags(tags: Dict[str, str]) -> Dict[str, str]:
    filtered_tags = {}
    for k, v in tags.items():
        if not _is_valid_tag(k, v):
            logger.warning("Skipping invalid tag '%s: %s'", k, v)
            continue
        filtered_tags[k] = v
    return filtered_tags


def validate_tags(tags: Dict[str, str]):
    for k, v in tags.items():
        if not _is_valid_tag(k, v):
            raise BackendError(
                "Invalid Azure resource tags. "
                "See tags restrictions: https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/tag-resources#limitations"
            )


def _is_valid_tag(key: str, value: str) -> bool:
    return _is_valid_tag_key(key) and _is_valid_tag_value(value)


TAG_KEY_PATTERN = re.compile(r"^(?!.*[<>&\\%?\/]).{1,512}$")
TAG_VALUE_PATTERN = re.compile(r".{0,256}$")


def _is_valid_tag_key(key: str) -> bool:
    return TAG_KEY_PATTERN.match(key) is not None


def _is_valid_tag_value(value: str) -> bool:
    return TAG_VALUE_PATTERN.match(value) is not None
