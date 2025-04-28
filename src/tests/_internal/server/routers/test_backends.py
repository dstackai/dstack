import json
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, Optional
from unittest.mock import Mock, patch

import pytest
import yaml
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.backends.oci import region as oci_region
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.core.models.volumes import VolumeStatus
from dstack._internal.server.models import BackendModel
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.testing.common import (
    create_backend,
    create_fleet,
    create_instance,
    create_project,
    create_user,
    create_volume,
    get_auth_headers,
    get_volume_provisioning_data,
)
from dstack._internal.utils.crypto import generate_rsa_key_pair_bytes

FAKE_NEBIUS_SERVICE_ACCOUNT_CREDS = {
    "type": "service_account",
    "service_account_id": "serviceaccount-e00test",
    "public_key_id": "publickey-e00test",
    "private_key_content": generate_rsa_key_pair_bytes()[0].decode(),
}
FAKE_OCI_CLIENT_CREDS = {
    "type": "client",
    "user": "ocid1.user.oc1..aaaaaaaa",
    "tenancy": "ocid1.tenancy.oc1..aaaaaaaa",
    "key_content": (
        "-----BEGIN PRIVATE KEY-----\n"
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        "-----END PRIVATE KEY-----"
    ),
    "fingerprint": "00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00",
    "region": "me-dubai-1",
}
SAMPLE_OCI_COMPARTMENT_ID = "ocid1.compartment.oc1..aaaaaaaa"
SAMPLE_OCI_SUBSCRIBED_REGIONS = oci_region.SubscribedRegions(
    names={"me-dubai-1", "eu-frankfurt-1"}, home_region_name="eu-frankfurt-1"
)
SAMPLE_OCI_SUBNETS = {
    "me-dubai-1": "ocid1.subnet.oc1.me-dubai-1.aaaaaaaa",
    "eu-frankfurt-1": "ocid1.subnet.oc1.eu-frankfurt-1.aaaaaaaa",
}


def _nebius_project(
    id: str = "project-e00test",
    name: str = "default-project-eu-north1",
    region: str = "eu-north1",
):
    project = Mock()
    project.metadata.id = id
    project.metadata.name = name
    project.status.region = region
    return project


class TestListBackendTypes:
    @pytest.mark.asyncio
    async def test_returns_backend_types(self, client: AsyncClient):
        response = await client.post("/api/backends/list_types")
        assert response.status_code == 200, response.json()
        assert response.json() == [
            "aws",
            "azure",
            "cudo",
            "datacrunch",
            "gcp",
            "kubernetes",
            "lambda",
            *(["nebius"] if sys.version_info >= (3, 10) else []),
            "oci",
            "runpod",
            "tensordock",
            "vastai",
            "vultr",
        ]


class TestCreateBackend:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_403_if_not_admin(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = await client.post(
            f"/api/project/{project.name}/backends/create",
            headers=get_auth_headers(user.token),
            json={},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_creates_aws_backend(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        body = {
            "type": "aws",
            "creds": {
                "type": "access_key",
                "access_key": "1234",
                "secret_key": "1234",
            },
            "regions": ["us-west-1"],
        }
        with (
            patch("dstack._internal.core.backends.aws.auth.authenticate"),
            patch("dstack._internal.core.backends.aws.compute.get_vpc_id_subnet_id_or_error"),
        ):
            response = await client.post(
                f"/api/project/{project.name}/backends/create",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 200, response.json()
        res = await session.execute(select(BackendModel))
        assert len(res.scalars().all()) == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_creates_gcp_backend(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        body = {
            "type": "gcp",
            "creds": {
                "type": "service_account",
                "filename": "1234",
                "data": "1234",
            },
            "project_id": "test_project",
            "regions": ["us-east1"],
        }
        with (
            patch("dstack._internal.core.backends.gcp.auth.authenticate") as authenticate_mock,
            patch("dstack._internal.core.backends.gcp.resources.check_vpc") as check_vpc_mock,
        ):
            credentials_mock = Mock()
            authenticate_mock.return_value = credentials_mock, "test_project"
            response = await client.post(
                f"/api/project/{project.name}/backends/create",
                headers=get_auth_headers(user.token),
                json=body,
            )
            check_vpc_mock.assert_called()
        assert response.status_code == 200, response.json()
        res = await session.execute(select(BackendModel))
        assert len(res.scalars().all()) == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_creates_lambda_backend(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        body = {
            "type": "lambda",
            "creds": {
                "type": "api_key",
                "api_key": "1234",
            },
            "regions": ["asd"],
        }
        with patch("dstack._internal.core.backends.lambdalabs.api_client.LambdaAPIClient") as m:
            m.return_value.validate_api_key.return_value = True
            response = await client.post(
                f"/api/project/{project.name}/backends/create",
                headers=get_auth_headers(user.token),
                json=body,
            )
            m.return_value.validate_api_key.assert_called()
        assert response.status_code == 200, response.json()
        res = await session.execute(select(BackendModel))
        assert len(res.scalars().all()) == 1

    @pytest.mark.asyncio
    @pytest.mark.skipif(sys.version_info < (3, 10), reason="Nebius requires Python 3.10")
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    class TestNebius:
        async def test_not_creates_with_invalid_creds(
            self, test_db, session: AsyncSession, client: AsyncClient
        ):
            user = await create_user(session=session, global_role=GlobalRole.USER)
            project = await create_project(session=session, owner=user)
            await add_project_member(
                session=session, project=project, user=user, project_role=ProjectRole.ADMIN
            )
            body = {
                "type": "nebius",
                "creds": FAKE_NEBIUS_SERVICE_ACCOUNT_CREDS,
            }
            with patch(
                "dstack._internal.core.backends.nebius.resources.list_tenant_projects"
            ) as projects_mock:
                projects_mock.side_effect = ValueError()
                response = await client.post(
                    f"/api/project/{project.name}/backends/create",
                    headers=get_auth_headers(user.token),
                    json=body,
                )
            assert response.status_code == 400, response.json()
            res = await session.execute(select(BackendModel))
            assert len(res.scalars().all()) == 0

        @pytest.mark.parametrize(
            ("config_regions", "config_projects", "mocked_projects", "error"),
            [
                pytest.param(
                    None,
                    None,
                    [_nebius_project()],
                    None,
                    id="default",
                ),
                pytest.param(
                    ["eu-north1"],
                    None,
                    [
                        _nebius_project(
                            "project-e00test", "default-project-eu-north1", "eu-north1"
                        ),
                        _nebius_project("project-e01test", "default-project-eu-west1", "eu-west1"),
                    ],
                    None,
                    id="with-regions",
                ),
                pytest.param(
                    ["xx-xxxx1"],
                    None,
                    [_nebius_project()],
                    "do not exist in this Nebius tenancy",
                    id="error-invalid-regions",
                ),
                pytest.param(
                    ["eu-north1"],
                    None,
                    [
                        _nebius_project(
                            "project-e00test0", "default-project-eu-north1", "eu-north1"
                        ),
                        _nebius_project("project-e00test1", "non-default-project", "eu-north1"),
                    ],
                    None,
                    id="finds-default-project-among-many",
                ),
                pytest.param(
                    ["eu-north1"],
                    None,
                    [
                        _nebius_project("project-e00test0", "non-default-project-0", "eu-north1"),
                        _nebius_project("project-e00test1", "non-default-project-1", "eu-north1"),
                    ],
                    "Could not find the default project in region eu-north1",
                    id="error-no-default-project",
                ),
                pytest.param(
                    None,
                    ["project-e00test0"],
                    [
                        _nebius_project("project-e00test0", "non-default-project-0", "eu-north1"),
                        _nebius_project("project-e00test1", "non-default-project-1", "eu-north1"),
                    ],
                    None,
                    id="with-projects",
                ),
                pytest.param(
                    None,
                    ["project-e00xxxx"],
                    [_nebius_project()],
                    "not found in this Nebius tenancy",
                    id="error-invalid-projects",
                ),
                pytest.param(
                    None,
                    ["project-e00test0", "project-e00test1"],
                    [
                        _nebius_project("project-e00test0", "non-default-project-0", "eu-north1"),
                        _nebius_project("project-e00test1", "non-default-project-1", "eu-north1"),
                    ],
                    "both belong to the same region",
                    id="error-multiple-projects-in-same-region",
                ),
                pytest.param(
                    ["eu-north1"],
                    ["project-e00test"],
                    [
                        _nebius_project(
                            "project-e00test", "default-project-eu-north1", "eu-north1"
                        ),
                        _nebius_project("project-e01test", "default-project-eu-west1", "eu-west1"),
                    ],
                    None,
                    id="with-regions-and-projects",
                ),
            ],
        )
        async def test_create(
            self,
            test_db,
            session: AsyncSession,
            client: AsyncClient,
            config_regions: Optional[list[str]],
            config_projects: Optional[list[str]],
            mocked_projects: Sequence[Any],
            error: Optional[str],
        ):
            user = await create_user(session=session, global_role=GlobalRole.USER)
            project = await create_project(session=session, owner=user)
            await add_project_member(
                session=session, project=project, user=user, project_role=ProjectRole.ADMIN
            )
            body = {
                "type": "nebius",
                "creds": FAKE_NEBIUS_SERVICE_ACCOUNT_CREDS,
                "regions": config_regions,
                "projects": config_projects,
            }
            with patch(
                "dstack._internal.core.backends.nebius.resources.list_tenant_projects"
            ) as projects_mock:
                projects_mock.return_value = mocked_projects
                response = await client.post(
                    f"/api/project/{project.name}/backends/create",
                    headers=get_auth_headers(user.token),
                    json=body,
                )
            if not error:
                assert response.status_code == 200, response.json()
                res = await session.execute(select(BackendModel))
                assert len(res.scalars().all()) == 1
            else:
                assert response.status_code == 400, response.json()
                assert error in response.json()["detail"][0]["msg"]
                res = await session.execute(select(BackendModel))
                assert len(res.scalars().all()) == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_creates_oci_backend(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        body = {
            "type": "oci",
            "creds": FAKE_OCI_CLIENT_CREDS,
        }
        with (
            patch(
                "dstack._internal.core.backends.oci.configurator.get_subscribed_regions"
            ) as get_regions_mock,
            patch(
                "dstack._internal.core.backends.oci.configurator._create_resources"
            ) as create_resources_mock,
        ):
            get_regions_mock.return_value = SAMPLE_OCI_SUBSCRIBED_REGIONS
            create_resources_mock.return_value = SAMPLE_OCI_COMPARTMENT_ID, SAMPLE_OCI_SUBNETS
            response = await client.post(
                f"/api/project/{project.name}/backends/create",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 200, response.json()
        res = await session.execute(select(BackendModel))
        assert len(res.scalars().all()) == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_not_creates_oci_backend_if_regions_not_subscribed(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        body = {
            "type": "oci",
            "creds": FAKE_OCI_CLIENT_CREDS,
            "regions": ["me-dubai-1", "eu-frankfurt-1", "us-ashburn-1"],
        }
        with (
            patch(
                "dstack._internal.core.backends.oci.configurator.get_subscribed_regions"
            ) as get_regions_mock,
        ):
            # us-ashburn-1 not subscribed
            get_regions_mock.return_value = SAMPLE_OCI_SUBSCRIBED_REGIONS
            response = await client.post(
                f"/api/project/{project.name}/backends/create",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 400, response.json()
        res = await session.execute(select(BackendModel))
        assert len(res.scalars().all()) == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_create_azure_backend(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        body = {
            "type": "azure",
            "creds": {
                "type": "client",
                "tenant_id": "test_tenant",
                "client_id": "1234",
                "client_secret": "1234",
            },
            "tenant_id": "test_tenant",
            "subscription_id": "test_subscription",
            "regions": ["eastus"],
        }
        with (
            patch("dstack._internal.core.backends.azure.auth.authenticate") as authenticate_mock,
            patch("azure.mgmt.subscription.SubscriptionClient") as SubscriptionClientMock,
            patch("azure.mgmt.resource.ResourceManagementClient") as ResourceManagementClientMock,
            patch("azure.mgmt.network.NetworkManagementClient") as NetworkManagementClientMock,
        ):
            authenticate_mock.return_value = None, "test_tenant"
            subscription_client_mock = SubscriptionClientMock.return_value
            tenant_mock = Mock()
            tenant_mock.tenant_id = "test_tenant"
            subscription_client_mock.tenants.list.return_value = [tenant_mock]
            subscription_mock = Mock()
            subscription_mock.subscription_id = "test_subscription"
            subscription_mock.display_name = "Subscription"
            subscription_client_mock.subscriptions.list.return_value = [subscription_mock]
            resource_client_mock = ResourceManagementClientMock.return_value
            resource_group_mock = Mock()
            resource_group_mock.name = "test_resource_group"
            resource_client_mock.resource_groups.create_or_update.return_value = (
                resource_group_mock
            )
            response = await client.post(
                f"/api/project/{project.name}/backends/create",
                headers=get_auth_headers(user.token),
                json=body,
            )
            authenticate_mock.assert_called()
            SubscriptionClientMock.assert_called()
            ResourceManagementClientMock.assert_called()
            NetworkManagementClientMock.assert_called()
        assert response.status_code == 200, response.json()
        res = await session.execute(select(BackendModel))
        assert len(res.scalars().all()) == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_400_if_backend_exists(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        body = {
            "type": "aws",
            "creds": {
                "type": "access_key",
                "access_key": "1234",
                "secret_key": "1234",
            },
            "regions": ["us-west-1"],
        }
        with (
            patch("dstack._internal.core.backends.aws.auth.authenticate"),
            patch("dstack._internal.core.backends.aws.compute.get_vpc_id_subnet_id_or_error"),
        ):
            response = await client.post(
                f"/api/project/{project.name}/backends/create",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 200, response.json()
        res = await session.execute(select(BackendModel))
        assert len(res.scalars().all()) == 1
        with (
            patch("dstack._internal.core.backends.aws.auth.authenticate") as authenticate_mock,  # noqa: F841
        ):
            response = await client.post(
                f"/api/project/{project.name}/backends/create",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 400, response.json()
        res = await session.execute(select(BackendModel))
        assert len(res.scalars().all()) == 1


class TestUpdateBackend:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_403_if_not_admin(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = await client.post(
            f"/api/project/{project.name}/backends/update",
            headers=get_auth_headers(user.token),
            json={},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_updates_backend(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        backend = await create_backend(
            session=session, project_id=project.id, config={"regions": ["us-west-1"]}
        )
        body = {
            "type": "aws",
            "creds": {
                "type": "access_key",
                "access_key": "1234",
                "secret_key": "1234",
            },
            "regions": ["us-east-1"],
        }
        with (
            patch("dstack._internal.core.backends.aws.auth.authenticate"),
            patch("dstack._internal.core.backends.aws.compute.get_vpc_id_subnet_id_or_error"),
        ):
            response = await client.post(
                f"/api/project/{project.name}/backends/update",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 200, response.json()
        await session.refresh(backend)
        assert json.loads(backend.config)["regions"] == ["us-east-1"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_400_if_backend_does_not_exist(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        body = {
            "type": "aws",
            "creds": {
                "type": "access_key",
                "access_key": "1234",
                "secret_key": "1234",
            },
            "regions": ["us-east-1"],
        }
        response = await client.post(
            f"/api/project/{project.name}/backends/update",
            headers=get_auth_headers(user.token),
            json=body,
        )
        assert response.status_code == 400


class TestDeleteBackends:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_403_if_not_admin(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = await client.post(
            f"/api/project/{project.name}/backends/delete",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_deletes_backends(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        backend = await create_backend(session=session, project_id=project.id)
        response = await client.post(
            f"/api/project/{project.name}/backends/delete",
            headers=get_auth_headers(user.token),
            json={"backends_names": [backend.type.value]},
        )
        assert response.status_code == 200, response.json()
        res = await session.execute(select(BackendModel))
        assert len(res.scalars().all()) == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_400_if_backend_has_active_instances(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        backend = await create_backend(session=session, project_id=project.id)
        fleet = await create_fleet(session=session, project=project)
        instance1 = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.TERMINATED,
            backend=backend.type,
        )
        instance2 = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.IDLE,
            backend=backend.type,
        )
        fleet.instances.append(instance1)
        fleet.instances.append(instance2)
        await session.commit()
        response = await client.post(
            f"/api/project/{project.name}/backends/delete",
            headers=get_auth_headers(user.token),
            json={"backends_names": [backend.type.value]},
        )
        assert response.status_code == 400
        res = await session.execute(select(BackendModel))
        assert len(res.scalars().all()) == 1
        fleet.instances.pop()
        await session.commit()
        response = await client.post(
            f"/api/project/{project.name}/backends/delete",
            headers=get_auth_headers(user.token),
            json={"backends_names": [backend.type.value]},
        )
        assert response.status_code == 200
        res = await session.execute(select(BackendModel))
        assert len(res.scalars().all()) == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_400_if_backend_has_active_volumes(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        backend = await create_backend(session=session, project_id=project.id)
        await create_volume(
            session=session,
            project=project,
            user=user,
            backend=backend.type,
            volume_provisioning_data=get_volume_provisioning_data(backend=backend.type),
            status=VolumeStatus.ACTIVE,
            deleted_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        volume2 = await create_volume(
            session=session,
            project=project,
            user=user,
            backend=backend.type,
            volume_provisioning_data=get_volume_provisioning_data(backend=backend.type),
            status=VolumeStatus.ACTIVE,
        )
        await session.commit()
        response = await client.post(
            f"/api/project/{project.name}/backends/delete",
            headers=get_auth_headers(user.token),
            json={"backends_names": [backend.type.value]},
        )
        assert response.status_code == 400
        res = await session.execute(select(BackendModel))
        assert len(res.scalars().all()) == 1
        await session.delete(volume2)
        await session.commit()
        response = await client.post(
            f"/api/project/{project.name}/backends/delete",
            headers=get_auth_headers(user.token),
            json={"backends_names": [backend.type.value]},
        )
        assert response.status_code == 200
        res = await session.execute(select(BackendModel))
        assert len(res.scalars().all()) == 0


class TestGetConfigInfo:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_403_if_not_admin(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        backend = await create_backend(session=session, project_id=project.id)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = await client.post(
            f"/api/project/{project.name}/backends/{backend.type.value}/config_info",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_config_info(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        backend = await create_backend(session=session, project_id=project.id)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        response = await client.post(
            f"/api/project/{project.name}/backends/{backend.type.value}/config_info",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200, response.json()
        assert response.json() == {
            "type": "aws",
            "regions": json.loads(backend.config)["regions"],
            "vpc_name": None,
            "vpc_ids": None,
            "default_vpcs": None,
            "public_ips": None,
            "iam_instance_profile": None,
            "tags": None,
            "os_images": None,
            "creds": json.loads(backend.auth.plaintext),
        }


class TestCreateBackendYAML:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_403_if_not_admin(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = await client.post(
            f"/api/project/{project.name}/backends/create_yaml",
            headers=get_auth_headers(user.token),
            json={},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_creates_aws_backend(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        config_dict = {
            "type": "aws",
            "creds": {
                "type": "access_key",
                "access_key": "1234",
                "secret_key": "1234",
            },
            "regions": ["us-west-1"],
        }
        body = {"config_yaml": yaml.dump(config_dict)}
        with (
            patch("dstack._internal.core.backends.aws.auth.authenticate"),
            patch("dstack._internal.core.backends.aws.compute.get_vpc_id_subnet_id_or_error"),
        ):
            response = await client.post(
                f"/api/project/{project.name}/backends/create_yaml",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 200, response.json()
        res = await session.execute(select(BackendModel))
        assert len(res.scalars().all()) == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_creates_oci_backend(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        config_dict = {
            "type": "oci",
            "creds": FAKE_OCI_CLIENT_CREDS,
        }
        body = {"config_yaml": yaml.dump(config_dict)}
        with (
            patch(
                "dstack._internal.core.backends.oci.configurator.get_subscribed_regions"
            ) as get_regions_mock,
            patch(
                "dstack._internal.core.backends.oci.configurator._create_resources"
            ) as create_resources_mock,
        ):
            get_regions_mock.return_value = SAMPLE_OCI_SUBSCRIBED_REGIONS
            create_resources_mock.return_value = SAMPLE_OCI_COMPARTMENT_ID, SAMPLE_OCI_SUBNETS
            response = await client.post(
                f"/api/project/{project.name}/backends/create_yaml",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 200, response.json()
        res = await session.execute(select(BackendModel))
        assert len(res.scalars().all()) == 1


class TestUpdateBackendYAML:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_403_if_not_admin(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = await client.post(
            f"/api/project/{project.name}/backends/update_yaml",
            headers=get_auth_headers(user.token),
            json={},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_updates_aws_backend(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        backend = await create_backend(
            session=session,
            project_id=project.id,
            backend_type=BackendType.AWS,
            config={"regions": ["us-west-1"]},
        )
        config_dict = {
            "type": "aws",
            "creds": {
                "type": "access_key",
                "access_key": "1234",
                "secret_key": "1234",
            },
            "regions": ["us-east-1"],
        }
        body = {"config_yaml": yaml.dump(config_dict)}
        with (
            patch("dstack._internal.core.backends.aws.auth.authenticate"),
            patch("dstack._internal.core.backends.aws.compute.get_vpc_id_subnet_id_or_error"),
        ):
            response = await client.post(
                f"/api/project/{project.name}/backends/update_yaml",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 200, response.json()
        await session.refresh(backend)
        assert json.loads(backend.config)["regions"] == ["us-east-1"]


class TestGetConfigYAML:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_403_if_not_admin(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        await create_backend(
            session=session,
            project_id=project.id,
            backend_type=BackendType.AWS,
            config={"regions": ["us-west-1"]},
        )
        response = await client.post(
            f"/api/project/{project.name}/backends/aws/get_yaml",
            headers=get_auth_headers(user.token),
            json={},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_config_yaml(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        auth = {
            "type": "access_key",
            "access_key": "test_access_key",
            "secret_key": "test_secret_key",
        }
        config = {"regions": ["us-west-1"]}
        await create_backend(
            session=session,
            project_id=project.id,
            backend_type=BackendType.AWS,
            config=config,
            auth=auth,
        )
        response = await client.post(
            f"/api/project/{project.name}/backends/aws/get_yaml",
            headers=get_auth_headers(user.token),
            json={},
        )
        expected_config_yaml = (
            "type: aws\n"
            "regions: [us-west-1]\n"
            "creds:\n"
            "  type: access_key\n"
            "  access_key: test_access_key\n"
            "  secret_key: test_secret_key\n"
        )
        assert response.status_code == 200
        assert response.json() == {"name": "aws", "config_yaml": expected_config_yaml}
