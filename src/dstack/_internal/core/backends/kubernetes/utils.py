from typing import Callable, Optional, TypeVar, Union

import yaml
from kubernetes.client import CoreV1Api
from kubernetes.client.exceptions import ApiException
from kubernetes.config import (
    # XXX: This function is missing in the stubs package
    new_client_from_config_dict,  # pyright: ignore[reportAttributeAccessIssue]
)
from typing_extensions import ParamSpec

from dstack._internal.utils.common import get_or_error

T = TypeVar("T")
P = ParamSpec("P")


def get_api_from_config_data(kubeconfig_data: str) -> CoreV1Api:
    config_dict = yaml.load(kubeconfig_data, yaml.FullLoader)
    return get_api_from_config_dict(config_dict)


def get_api_from_config_dict(kubeconfig: dict) -> CoreV1Api:
    api_client = new_client_from_config_dict(config_dict=kubeconfig)
    return CoreV1Api(api_client=api_client)


def call_api_method(
    method: Callable[P, T],
    expected: Union[int, tuple[int, ...], list[int]],
    *args: P.args,
    **kwargs: P.kwargs,
) -> Optional[T]:
    """
    Returns the result of the API method call ignoring specified HTTP status codes.

    If you don't expect any error status code, just call the method directly.

    Args:
        method: the `CoreV1Api` bound method.
        expected: Expected error statuses, e.g., 404.
        args: positional arguments of the method.
        kwargs: keyword arguments of the method.
    Returns:
        The return value or `None` in case of the expected error.
    """
    if isinstance(expected, int):
        expected = (expected,)
    try:
        return method(*args, **kwargs)
    except ApiException as e:
        if e.status not in expected:
            raise
    return None


def get_cluster_public_ip(api: CoreV1Api) -> Optional[str]:
    """
    Returns public IP of any cluster node.
    """
    public_ips = get_cluster_public_ips(api)
    if len(public_ips) == 0:
        return None
    return public_ips[0]


def get_cluster_public_ips(api: CoreV1Api) -> list[str]:
    """
    Returns public IPs of all cluster nodes.
    """
    public_ips = []
    for node in api.list_node().items:
        node_status = get_or_error(node.status)
        addresses = get_or_error(node_status.addresses)

        # Look for an external IP address
        for address in addresses:
            if address.type == "ExternalIP":
                public_ips.append(address.address)

    return public_ips
