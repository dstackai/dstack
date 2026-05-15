from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Annotated, Any, Callable, Generic, Literal, Optional, Protocol, TypeVar, Union
from uuid import UUID

import yaml
from cachetools import TTLCache
from kubernetes.client import V1Status, VersionApi
from kubernetes.client.exceptions import ApiException

# XXX: The watch module is missing in the stubs package
from kubernetes.watch import Watch  # pyright: ignore[reportMissingImports]
from pydantic import Field
from typing_extensions import ParamSpec, TypedDict

from dstack._internal.core.backends.kubernetes.api_client import (
    API_CLIENT_EXCEPTIONS,
    ApiClient,
    get_api_client_from_kubeconfig_dict,
)
from dstack._internal.core.backends.kubernetes.models import (
    KubernetesBackendConfigWithCreds,
    KubernetesProxyJumpConfig,
)
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.instances import InstanceOffer
from dstack._internal.core.models.runs import Job, Run
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")
P = ParamSpec("P")


LEGACY_CURRENT_CONTEXT_REGION = ""


@dataclass
class Cluster:
    context_name: str
    region: str
    api_client: ApiClient
    namespace: str
    proxy_jump: KubernetesProxyJumpConfig

    def __str__(self) -> str:
        parts: list[str] = []
        parts.append(f"context={self.context_name!r}")
        if self.context_name != self.region:
            parts.append(f"region={self.region!r}")
        return f"({' '.join(parts)})"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}{self}"


def check_cluster(cluster: Cluster) -> bool:
    version_api = VersionApi(cluster.api_client)
    try:
        version_info = version_api.get_code()
    except API_CLIENT_EXCEPTIONS as e:
        logger.debug("cluster %s check failed: %s: %s", cluster, e.__class__.__name__, e)
        return False
    logger.debug("cluster %s gitVersion: %s", cluster, version_info.git_version)
    return True


def get_clusters_from_backend_config(
    config: KubernetesBackendConfigWithCreds,
    *,
    request_timeout: Optional[int] = None,
    retries: Optional[int] = None,
) -> list[Cluster]:
    clusters: list[Cluster] = []
    kubeconfig_dict = kubeconfig_data_to_kubeconfig_dict(config.kubeconfig.data)
    kubeconfig = kubeconfig_dict_to_kubeconfig(kubeconfig_dict)
    if config.contexts is not None:
        for context in config.contexts:
            if isinstance(context, str):
                context_name = context
                proxy_jump = None
            else:
                context_name = context.name
                proxy_jump = context.proxy_jump
            kubeconfig_context = kubeconfig.get_context(context_name)
            api_client = get_api_client_from_kubeconfig_dict(
                kubeconfig_dict,
                context=context_name,
                request_timeout=request_timeout,
                retries=retries,
            )
            namespace = kubeconfig_context.namespace
            if proxy_jump is None:
                proxy_jump = KubernetesProxyJumpConfig()
            clusters.append(
                Cluster(
                    context_name=context_name,
                    region=context_name,
                    api_client=api_client,
                    namespace=namespace,
                    proxy_jump=proxy_jump,
                )
            )
    else:
        current_kubeconfig_context = kubeconfig.get_context()
        context_name = kubeconfig.current_context
        # Already checked by Kubeconfig.get_context()
        assert context_name is not None
        api_client = get_api_client_from_kubeconfig_dict(
            kubeconfig_dict,
            context=context_name,
            request_timeout=request_timeout,
            retries=retries,
        )
        config_namespace = config.namespace
        if config_namespace is None:
            config_namespace = "default"
        context_namespace = current_kubeconfig_context.namespace
        if context_namespace != config_namespace:
            logger.warning(
                (
                    "Namespace mismatch: kubeconfig -> '%s', backend config -> '%s'."
                    " The current dstack version ignores kubeconfig"
                    " and uses deprecated namespace property from backend config."
                    " Future versions will use namespace from kubeconfig."
                    " To keep using '%s' namespace in future versions and suppress this warning,"
                    " set namespace to '%s' in kubeconfig context '%s'"
                ),
                context_namespace,
                config_namespace,
                config_namespace,
                config_namespace,
                context_name,
            )
        proxy_jump = config.proxy_jump
        if proxy_jump is None:
            proxy_jump = KubernetesProxyJumpConfig()
        clusters.append(
            Cluster(
                context_name=context_name,
                region=LEGACY_CURRENT_CONTEXT_REGION,
                api_client=api_client,
                # TODO: switch to context_namespace
                namespace=config_namespace,
                proxy_jump=proxy_jump,
            )
        )
    return clusters


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


class SkipOfferCache:
    """
    `SkipOfferCache` is used to track (run/job, offer) pairs that failed to provision.

    The current implementation tracks _any_ job of the specific run (identified by `Run.id`)
    on the specific cluster (identified by `InstanceOffer.region`, that is, a kubeconfig context).
    """

    def __init__(self, *, ttl: int, maxsize: int = 1000) -> None:
        self._cache = TTLCache[tuple[UUID, str], Literal[True]](maxsize=maxsize, ttl=ttl)

    def add(self, run: Run, job: Job, offer: InstanceOffer) -> None:
        self._cache[self._build_key(run, job, offer)] = True

    def check(self, run: Run, job: Job, offer: InstanceOffer) -> bool:
        return self._build_key(run, job, offer) in self._cache

    def _build_key(self, run: Run, job: Job, offer: InstanceOffer) -> tuple[UUID, str]:
        # The current implementation uses only Run.id ignoring the job/job spec.
        # A more sophisticated implementation could use some parts of the job spec
        # (e.g., requirements, volumes) instead.
        return (run.id, offer.region)


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
    except API_CLIENT_EXCEPTIONS as e:
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
    gen = _watch_events_gen(watch.stream(method, *args, **kwargs))
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


def _watch_events_gen(
    gen: Generator[Union[_StateEventDict[T], _BookmarkEventDict[T], _ErrorEventDict], None, None],
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
