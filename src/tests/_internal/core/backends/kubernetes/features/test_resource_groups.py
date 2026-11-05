from collections.abc import Generator
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import Mock, patch

import pytest
from kubernetes import client
from kubernetes.client.exceptions import ApiException

from dstack._internal.core.backends.kubernetes.features.resource_groups import (
    delete_resource_group,
    list_resource_groups,
)
from dstack._internal.core.backends.kubernetes.models import KubernetesProxyJumpConfig
from dstack._internal.core.backends.kubernetes.resources import build_base_labels
from dstack._internal.core.backends.kubernetes.utils import Cluster
from dstack._internal.core.errors import ComputeError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.backends.orphans import ListedResourceGroup, OwnerType

NAMESPACE = "dstack"
PROVIDER_REF = "abcdefgh1234"
JOB_POD_NAME = "dstack-run-0-0-abcd"
CREATED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _job_labels(pod_name: str = JOB_POD_NAME, provider_ref: str = PROVIDER_REF) -> dict[str, str]:
    return build_base_labels(
        component="job", unique_name=pod_name, project="main", provider_ref=provider_ref
    )


def _job_object_meta(
    name: str,
    *,
    labels: Optional[dict[str, str]] = None,
    created_at: datetime = CREATED_AT,
    terminating: bool = False,
) -> client.V1ObjectMeta:
    return client.V1ObjectMeta(
        name=name,
        labels=labels if labels is not None else _job_labels(),
        creation_timestamp=created_at,
        deletion_timestamp=CREATED_AT if terminating else None,
    )


def _object_list(items: list, continue_token: Optional[str] = None) -> Mock:
    return Mock(items=items, metadata=client.V1ListMeta(_continue=continue_token))


def _cluster(region: str = "ctx") -> Cluster:
    return Cluster(
        context_name=region,
        region=region,
        api_client=Mock(name=f"api_client_{region}"),
        namespace=NAMESPACE,
        proxy_jump=KubernetesProxyJumpConfig(),
    )


class TestListResourceGroups:
    @pytest.fixture
    def api(self) -> Generator[Mock, None, None]:
        api = Mock()
        api.list_namespaced_pod.return_value = _object_list([])
        api.list_namespaced_service.return_value = _object_list([])
        api.list_namespaced_secret.return_value = _object_list([])
        with patch(
            "dstack._internal.core.backends.kubernetes.features.resource_groups.client.CoreV1Api",
            return_value=api,
        ):
            yield api

    def test_groups_pod_with_its_service_and_secret(self, api: Mock):
        api.list_namespaced_pod.return_value = _object_list(
            [
                client.V1Pod(
                    metadata=_job_object_meta(JOB_POD_NAME),
                    status=client.V1PodStatus(phase="Running"),
                )
            ]
        )
        api.list_namespaced_service.return_value = _object_list(
            [client.V1Service(metadata=_job_object_meta(f"{JOB_POD_NAME}-service"))]
        )
        api.list_namespaced_secret.return_value = _object_list(
            [client.V1Secret(metadata=_job_object_meta(f"{JOB_POD_NAME}-registry-auth"))]
        )

        listing = list_resource_groups([_cluster()])

        assert listing.failures == []
        assert len(listing.resource_groups) == 1
        group = listing.resource_groups[0]
        assert group.provider_ref == PROVIDER_REF
        assert group.primary_id == JOB_POD_NAME
        assert group.region == "ctx"
        assert group.created_at == CREATED_AT
        assert group.description == (
            f"pod {JOB_POD_NAME} (Running), service {JOB_POD_NAME}-service,"
            f" secret {JOB_POD_NAME}-registry-auth"
        )
        api.list_namespaced_pod.assert_called_once_with(
            namespace=NAMESPACE,
            label_selector="k8s.dstack.ai/provider-ref",
            limit=500,
            _continue=None,
        )

    def test_lists_finished_pods(self, api: Mock):
        api.list_namespaced_pod.return_value = _object_list(
            [
                client.V1Pod(
                    metadata=_job_object_meta(JOB_POD_NAME),
                    status=client.V1PodStatus(phase="Succeeded"),
                )
            ]
        )

        listing = list_resource_groups([_cluster()])

        assert [g.primary_id for g in listing.resource_groups] == [JOB_POD_NAME]

    def test_lists_internal_objects_of_pod_being_deleted_without_pod(self, api: Mock):
        api.list_namespaced_pod.return_value = _object_list(
            [client.V1Pod(metadata=_job_object_meta(JOB_POD_NAME, terminating=True))]
        )
        api.list_namespaced_service.return_value = _object_list(
            [
                client.V1Service(
                    metadata=_job_object_meta(
                        f"{JOB_POD_NAME}-service", created_at=datetime(2026, 1, 2)
                    )
                )
            ]
        )

        listing = list_resource_groups([_cluster()])

        assert len(listing.resource_groups) == 1
        group = listing.resource_groups[0]
        assert group.primary_id is None
        assert group.created_at == datetime(2026, 1, 2)
        assert group.description == f"service {JOB_POD_NAME}-service"

    def test_skips_objects_without_valid_labels(self, api: Mock):
        labels_without_instance = _job_labels()
        del labels_without_instance["app.kubernetes.io/instance"]
        api.list_namespaced_pod.return_value = _object_list(
            [
                client.V1Pod(metadata=_job_object_meta("a", labels={})),
                client.V1Pod(metadata=_job_object_meta("b", labels=_job_labels(provider_ref="x"))),
                client.V1Pod(metadata=_job_object_meta("c", labels=labels_without_instance)),
            ]
        )

        listing = list_resource_groups([_cluster()])

        assert listing.resource_groups == []

    def test_separates_attempts_by_pod(self, api: Mock):
        api.list_namespaced_pod.return_value = _object_list(
            [
                client.V1Pod(metadata=_job_object_meta(name, labels=_job_labels(pod_name=name)))
                for name in ["pod-a", "pod-b"]
            ]
        )

        listing = list_resource_groups([_cluster()])

        assert sorted(g.primary_id or "" for g in listing.resource_groups) == ["pod-a", "pod-b"]
        assert {g.provider_ref for g in listing.resource_groups} == {PROVIDER_REF}

    def test_skips_services_and_secrets_if_listing_them_is_forbidden(self, api: Mock):
        api.list_namespaced_pod.return_value = _object_list(
            [client.V1Pod(metadata=_job_object_meta(JOB_POD_NAME))]
        )
        api.list_namespaced_service.side_effect = ApiException(status=403)
        api.list_namespaced_secret.side_effect = ApiException(status=403)

        listing = list_resource_groups([_cluster()])

        assert listing.failures == []
        assert [g.primary_id for g in listing.resource_groups] == [JOB_POD_NAME]

    def test_reports_cluster_failure(self, api: Mock):
        pods = [client.V1Pod(metadata=_job_object_meta(JOB_POD_NAME))]
        api.list_namespaced_pod.side_effect = [ApiException(status=403), _object_list(pods)]

        listing = list_resource_groups([_cluster("a"), _cluster("b")])

        assert [f.region for f in listing.failures] == ["a"]
        assert [g.region for g in listing.resource_groups] == ["b"]

    def test_fails_on_internal_object_listing_error_other_than_forbidden(self, api: Mock):
        api.list_namespaced_pod.return_value = _object_list(
            [client.V1Pod(metadata=_job_object_meta(JOB_POD_NAME))]
        )
        api.list_namespaced_secret.side_effect = ApiException(status=500)

        with pytest.raises(ComputeError):
            list_resource_groups([_cluster()])

    def test_raises_if_all_clusters_fail(self, api: Mock):
        api.list_namespaced_pod.side_effect = ApiException(status=500)

        with pytest.raises(ComputeError):
            list_resource_groups([_cluster("a"), _cluster("b")])


class TestDeleteResourceGroup:
    @pytest.fixture
    def api(self) -> Generator[Mock, None, None]:
        api = Mock()
        with patch(
            "dstack._internal.core.backends.kubernetes.features.resource_groups.client.CoreV1Api",
            return_value=api,
        ):
            yield api

    def group(self, primary_id: Optional[str] = JOB_POD_NAME) -> ListedResourceGroup:
        return ListedResourceGroup(
            backend=BackendType.KUBERNETES,
            owner_type=OwnerType.INSTANCE,
            provider_ref=PROVIDER_REF,
            primary_id=primary_id,
            region="ctx",
            created_at=CREATED_AT,
            description="",
            backend_data=f'{{"pod_name": "{JOB_POD_NAME}"}}',
        )

    @pytest.mark.parametrize("primary_id", [JOB_POD_NAME, None])
    def test_deletes_pod_service_and_secret(self, api: Mock, primary_id: Optional[str]):
        delete_resource_group({"ctx": _cluster()}, self.group(primary_id))

        api.delete_namespaced_service.assert_called_once_with(
            namespace=NAMESPACE, name=f"{JOB_POD_NAME}-service"
        )
        api.delete_namespaced_pod.assert_called_once_with(namespace=NAMESPACE, name=JOB_POD_NAME)
        api.delete_namespaced_secret.assert_called_once_with(
            namespace=NAMESPACE, name=f"{JOB_POD_NAME}-registry-auth"
        )

    def test_ignores_missing_objects(self, api: Mock):
        api.delete_namespaced_service.side_effect = ApiException(status=404)
        api.delete_namespaced_pod.side_effect = ApiException(status=404)
        api.delete_namespaced_secret.side_effect = ApiException(status=404)

        delete_resource_group({"ctx": _cluster()}, self.group())

    def test_raises_on_deletion_error(self, api: Mock):
        api.delete_namespaced_pod.side_effect = ApiException(status=500)

        with pytest.raises(ComputeError):
            delete_resource_group({"ctx": _cluster()}, self.group())

        api.delete_namespaced_secret.assert_called_once()
