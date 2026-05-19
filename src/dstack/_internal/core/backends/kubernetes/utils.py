from collections.abc import Generator
from contextlib import contextmanager
from typing import (
    Annotated,
    Any,
    Callable,
    Generic,
    Literal,
    Optional,
    Protocol,
    TypeVar,
    Union,
    cast,
)

import yaml
from kubernetes.client import CoreV1Api, V1Status
from kubernetes.client.exceptions import ApiException
from kubernetes.config import (
    # XXX: This function is missing in the stubs package
    new_client_from_config_dict,  # pyright: ignore[reportAttributeAccessIssue]
)
from kubernetes.watch import Watch
from pydantic import Field
from typing_extensions import ParamSpec, TypedDict
from urllib3.exceptions import HTTPError

from dstack._internal.core.models.common import CoreModel
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

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


class NamespacedNameMethod(Protocol):
    def __call__(self, name: str, namespace: str) -> Any: ...


def try_delete_object_if_exists(
    method: NamespacedNameMethod,
    *,
    namespace: str,
    name: str,
    description: str,
    should_delete_manually_if_failed: bool = False,
) -> bool:
    try:
        call_api_method(
            method,
            expected=404,
            namespace=namespace,
            name=name,
        )
    except (HTTPError, ApiException) as e:
        if should_delete_manually_if_failed:
            logger.exception(
                "Failed to delete %s %s in namespace %s. Please delete it manually",
                description,
                name,
                namespace,
            )
        else:
            logger.warning(
                "Failed to delete %s %s in namespace %s: %s: %s",
                description,
                name,
                namespace,
                e.__class__.__name__,
                e,
            )
        return False
    return True


class ObjectList(Protocol[T]):
    items: list[T]


@contextmanager
def watch_events(
    method: Callable[P, ObjectList[T]], *args: P.args, **kwargs: P.kwargs
) -> Generator[Generator[tuple[str, T], None, None], None, None]:
    watch = Watch()
    inner_gen = cast(Generator[_EventDict[T], None, None], watch.stream(method, *args, **kwargs))
    gen = _watch_events_gen(inner_gen)
    try:
        yield gen
    finally:
        gen.close()
        watch.stop()


class _StateEventDict(TypedDict, Generic[T]):
    type: Literal["ADDED", "MODIFIED", "DELETED"]
    object: T


class _BookmarkEventDict(TypedDict, Generic[T]):
    type: Literal["BOOKMARK"]
    # The object is a minimal instance of the watched resource's type -- same kind and apiVersion,
    # but only metadata.resourceVersion is populated. Everything else is empty or zero-valued.
    object: T


class _ErrorEventDict(TypedDict):
    type: Literal["ERROR"]
    object: V1Status


_EventDict = Union[_StateEventDict[T], _BookmarkEventDict[T], _ErrorEventDict]


def _watch_events_gen(
    gen: Generator[_EventDict[T], None, None],
) -> Generator[tuple[str, T], None, None]:
    try:
        for event in gen:
            match event["type"]:
                case "ADDED" | "MODIFIED" | "DELETED":
                    yield event["type"], event["object"]
                case "BOOKMARK":
                    pass
                case "ERROR":
                    status = event["object"]
                    logger.warning(
                        "Got ERROR event (status=%s reason=%s code=%s): %s",
                        status.status,
                        status.reason,
                        status.code,
                        status.message,
                    )
                case _:
                    logger.warning("Got unexpected event: %s", event)
    finally:
        gen.close()
