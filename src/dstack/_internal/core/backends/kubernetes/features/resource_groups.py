from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional, TypeVar

from kubernetes import client
from kubernetes.client.exceptions import ApiException

from dstack._internal.core.backends.base.compute import is_valid_provider_ref
from dstack._internal.core.backends.kubernetes.api_client import API_CLIENT_EXCEPTIONS
from dstack._internal.core.backends.kubernetes.resources import (
    INSTANCE_LABEL,
    PROVIDER_REF_LABEL,
    ObjectWithMeta,
    delete_job_pod_objects,
    get_object_labels,
    get_object_name,
)
from dstack._internal.core.backends.kubernetes.utils import (
    Cluster,
    ObjectListWithMeta,
    list_all_objects,
)
from dstack._internal.core.errors import ComputeError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.backends.orphans import (
    ListedResourceGroup,
    OwnerType,
    ResourceListing,
    ResourceListingFailure,
)
from dstack._internal.core.models.common import CoreModel, validate_json_extra_ignore
from dstack._internal.utils.common import get_or_error
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class KubernetesResourceGroupBackendData(CoreModel):
    pod_name: str
    """The job pod's name. The names of its service and secret are derived from it."""


def list_resource_groups(clusters: list[Cluster]) -> ResourceListing:
    """
    Each group is a job pod with its service and registry auth secret, listed by the
    `provider_ref` label in the namespace of each cluster.
    """
    resource_groups: list[ListedResourceGroup] = []
    failures: list[ResourceListingFailure] = []
    for cluster in clusters:
        try:
            resource_groups.extend(_list_cluster_resource_groups(cluster))
        except (*API_CLIENT_EXCEPTIONS, ComputeError) as e:
            failures.append(
                ResourceListingFailure(
                    backend=BackendType.KUBERNETES,
                    region=cluster.region,
                    message=f"Failed to list objects in cluster {cluster}: {e}",
                )
            )
    if len(failures) > 0 and len(failures) == len(clusters):
        raise ComputeError(f"Failed to list resources in all clusters: {failures}")
    return ResourceListing(resource_groups=resource_groups, failures=failures)


def delete_resource_group(
    clusters_by_region: dict[str, Cluster], group: ListedResourceGroup
) -> None:
    cluster = clusters_by_region.get(get_or_error(group.region))
    if cluster is None:
        raise ComputeError(f"Unknown region: {group.region!r}")
    backend_data = validate_json_extra_ignore(
        KubernetesResourceGroupBackendData, get_or_error(group.backend_data)
    )
    delete_job_pod_objects(
        api=client.CoreV1Api(cluster.api_client),
        namespace=cluster.namespace,
        pod_name=backend_data.pod_name,
    )


_T = TypeVar("_T")


@dataclass
class _JobPodObjects:
    provider_ref: str
    pod_name: str
    pod: Optional[client.V1Pod] = None
    internal_object_descriptions: list[str] = field(default_factory=list)
    created_at: Optional[datetime] = None

    def add_created_at(self, created_at: Optional[datetime]) -> None:
        if created_at is not None and (self.created_at is None or created_at < self.created_at):
            self.created_at = created_at


def _list_cluster_resource_groups(cluster: Cluster) -> list[ListedResourceGroup]:
    """
    Pods must be listed. Services and secrets are skipped with a warning if listing them is
    forbidden: groups with pods still delete them by their derived names, and only those left
    without pods are not found.
    """
    api = client.CoreV1Api(cluster.api_client)
    namespace = cluster.namespace
    pods = list_all_objects(
        api.list_namespaced_pod, namespace=namespace, label_selector=PROVIDER_REF_LABEL
    )
    services = _list_objects_with_provider_ref_if_permitted(
        api.list_namespaced_service, namespace, cluster=cluster, kind="services"
    )
    secrets = _list_objects_with_provider_ref_if_permitted(
        api.list_namespaced_secret, namespace, cluster=cluster, kind="secrets"
    )
    groups: dict[tuple[str, str], _JobPodObjects] = {}

    def get_group(obj: ObjectWithMeta) -> Optional[_JobPodObjects]:
        key = _get_job_pod_objects_key(obj, cluster)
        if key is None:
            return None
        if key not in groups:
            groups[key] = _JobPodObjects(provider_ref=key[0], pod_name=key[1])
        return groups[key]

    for pod in pods:
        metadata = get_or_error(pod.metadata)
        # The pod is being deleted; its service and secret are listed as usual.
        if metadata.deletion_timestamp is not None:
            continue
        group = get_group(pod)
        if group is None:
            continue
        group.pod = pod
        group.add_created_at(metadata.creation_timestamp)
    for kind, objects in (("service", services), ("secret", secrets)):
        for obj in objects:
            group = get_group(obj)
            if group is None:
                continue
            metadata = get_or_error(obj.metadata)
            group.internal_object_descriptions.append(f"{kind} {metadata.name}")
            if group.pod is None:
                group.add_created_at(metadata.creation_timestamp)
    return [_build_resource_group(group, cluster) for group in groups.values()]


def _list_objects_with_provider_ref_if_permitted(
    method: Callable[..., ObjectListWithMeta[_T]], namespace: str, *, cluster: Cluster, kind: str
) -> list[_T]:
    try:
        return list_all_objects(method, namespace=namespace, label_selector=PROVIDER_REF_LABEL)
    except ApiException as e:
        if e.status != 403:
            raise
    logger.warning(
        "Cannot list %s in namespace %s of cluster %s for orphan cleanup."
        " Grant the `list` verb on %s to clean up %s left without their pods",
        kind,
        namespace,
        cluster,
        kind,
        kind,
    )
    return []


def _get_job_pod_objects_key(obj: ObjectWithMeta, cluster: Cluster) -> Optional[tuple[str, str]]:
    labels = get_object_labels(obj)
    object_name = get_object_name(obj)
    provider_ref = labels.get(PROVIDER_REF_LABEL)
    if provider_ref is None:
        return None
    if not is_valid_provider_ref(provider_ref):
        logger.warning(
            "Skipping object %s in cluster %s with invalid %s label: %r",
            object_name,
            cluster,
            PROVIDER_REF_LABEL,
            provider_ref,
        )
        return None
    pod_name = labels.get(INSTANCE_LABEL)
    if pod_name is None:
        logger.warning(
            "Skipping object %s in cluster %s without %s label",
            object_name,
            cluster,
            INSTANCE_LABEL,
        )
        return None
    return provider_ref, pod_name


def _build_resource_group(group: _JobPodObjects, cluster: Cluster) -> ListedResourceGroup:
    description_parts: list[str] = []
    primary_id: Optional[str] = None
    if group.pod is not None:
        primary_id = group.pod_name
        phase = group.pod.status.phase if group.pod.status is not None else None
        description_parts.append(f"pod {group.pod_name} ({phase or 'unknown phase'})")
    description_parts.extend(group.internal_object_descriptions)
    return ListedResourceGroup(
        backend=BackendType.KUBERNETES,
        owner_type=OwnerType.INSTANCE,
        provider_ref=group.provider_ref,
        primary_id=primary_id,
        region=cluster.region,
        created_at=group.created_at,
        description=", ".join(description_parts),
        backend_data=KubernetesResourceGroupBackendData(pod_name=group.pod_name).model_dump_json(),
    )
