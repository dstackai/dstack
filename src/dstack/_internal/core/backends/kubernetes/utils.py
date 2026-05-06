from typing import Annotated, Callable, Optional, TypeVar, Union

import yaml
from kubernetes.client import CoreV1Api
from kubernetes.client.exceptions import ApiException
from kubernetes.config import (
    # XXX: This function is missing in the stubs package
    new_client_from_config_dict,  # pyright: ignore[reportAttributeAccessIssue]
)
from pydantic import Field
from typing_extensions import ParamSpec

from dstack._internal.core.models.common import CoreModel

T = TypeVar("T")
P = ParamSpec("P")


class KubeconfigContext(CoreModel):
    namespace: str = "default"


class KubeconfigNamedContext(CoreModel):
    name: str
    context: KubeconfigContext


class Kubeconfig(CoreModel):
    """
    `Kubeconfig` model only includes fields used by `dstack`.
    Reference: https://kubernetes.io/docs/reference/config-api/kubeconfig.v1/
    """

    contexts: list[KubeconfigNamedContext] = []
    current_context: Annotated[Optional[str], Field(alias="current-context")] = None

    def get_context(self, name: Optional[str] = None) -> KubeconfigContext:
        if name is None:
            name = self.current_context
            if name is None:
                raise ValueError("current-context is not set")
        for named_context in self.contexts:
            if named_context.name == name:
                return named_context.context
        raise ValueError(f"context {name} not found")


def kubeconfig_data_to_kubeconfig_dict(kubeconfig_data: str) -> dict:
    kubeconfig_dict = yaml.load(kubeconfig_data, yaml.FullLoader)
    if not isinstance(kubeconfig_dict, dict):
        raise TypeError(f"Unexpected kubeconfig_data type: {kubeconfig_dict.__class__.__name__}")
    return kubeconfig_dict


def kubeconfig_dict_to_kubeconfig(kubeconfig_dict: dict) -> Kubeconfig:
    return Kubeconfig.__response__.parse_obj(kubeconfig_dict)


def get_api_from_kubeconfig_data(
    kubeconfig_data: str, *, context: Optional[str] = None
) -> CoreV1Api:
    kubeconfig_dict = kubeconfig_data_to_kubeconfig_dict(kubeconfig_data)
    return get_api_from_kubeconfig_dict(kubeconfig_dict, context=context)


def get_api_from_kubeconfig_dict(
    kubeconfig_dict: dict, *, context: Optional[str] = None
) -> CoreV1Api:
    api_client = new_client_from_config_dict(config_dict=kubeconfig_dict, context=context)
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
