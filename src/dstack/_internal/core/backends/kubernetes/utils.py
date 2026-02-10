from typing import Callable, Optional, TypeVar, Union

import yaml
from kubernetes.client import CoreV1Api
from kubernetes.client.exceptions import ApiException
from kubernetes.config import (
    # XXX: This function is missing in the stubs package
    new_client_from_config_dict,  # pyright: ignore[reportAttributeAccessIssue]
)
from typing_extensions import ParamSpec

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
