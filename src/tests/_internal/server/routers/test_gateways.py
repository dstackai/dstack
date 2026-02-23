from unittest.mock import Mock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import DstackError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.testing.common import (
    ComputeMockSpec,
    clear_events,
    create_backend,
    create_gateway,
    create_gateway_compute,
    create_project,
    create_user,
    get_auth_headers,
    list_events,
)
from dstack._internal.server.testing.matchers import SomeUUID4Str
from dstack._internal.settings import FeatureFlags


@pytest.fixture
def patch_pipeline_processing_flag(monkeypatch: pytest.MonkeyPatch):
    def _apply(enabled: bool):
        monkeypatch.setattr(FeatureFlags, "PIPELINE_PROCESSING_ENABLED", enabled)

    return _apply


class TestListAndGetGateways:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_40x_if_not_authenticated(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        response = await client.post("/api/project/main/gateways/list")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_list(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        backend = await create_backend(session=session, project_id=project.id)
        gateway_compute = await create_gateway_compute(
            session=session,
            backend_id=backend.id,
        )
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            gateway_compute_id=gateway_compute.id,
        )
        response = await client.post(
            f"/api/project/{project.name}/gateways/list",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        assert response.json() == [
            {
                "id": SomeUUID4Str(),
                "backend": backend.type.value,
                "created_at": response.json()[0]["created_at"],
                "default": False,
                "status": "submitted",
                "status_message": None,
                "instance_id": gateway_compute.instance_id,
                "ip_address": gateway_compute.ip_address,
                "hostname": gateway_compute.ip_address,
                "name": gateway.name,
                "region": gateway.region,
                "wildcard_domain": gateway.wildcard_domain,
                "configuration": {
                    "type": "gateway",
                    "name": gateway.name,
                    "backend": backend.type.value,
                    "region": gateway.region,
                    "instance_type": None,
                    "router": None,
                    "domain": gateway.wildcard_domain,
                    "default": False,
                    "public_ip": True,
                    "certificate": {"type": "lets-encrypt"},
                    "tags": None,
                },
            }
        ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_get(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        backend = await create_backend(session, project.id)
        gateway_compute = await create_gateway_compute(
            session=session,
            backend_id=backend.id,
        )
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            gateway_compute_id=gateway_compute.id,
        )
        response = await client.post(
            f"/api/project/{project.name}/gateways/get",
            json={"name": gateway.name},
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        assert response.json() == {
            "id": SomeUUID4Str(),
            "backend": backend.type.value,
            "created_at": response.json()["created_at"],
            "default": False,
            "status": "submitted",
            "status_message": None,
            "instance_id": gateway_compute.instance_id,
            "ip_address": gateway_compute.ip_address,
            "hostname": gateway_compute.ip_address,
            "name": gateway.name,
            "region": gateway.region,
            "wildcard_domain": gateway.wildcard_domain,
            "configuration": {
                "type": "gateway",
                "name": gateway.name,
                "backend": backend.type.value,
                "region": gateway.region,
                "instance_type": None,
                "router": None,
                "domain": gateway.wildcard_domain,
                "default": False,
                "public_ip": True,
                "certificate": {"type": "lets-encrypt"},
                "tags": None,
            },
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_get_missing(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = await client.post(
            f"/api/project/{project.name}/gateways/get",
            json={"name": "missing"},
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 400


class TestCreateGateway:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_only_admin_can_create(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = await client.post(
            f"/api/project/{project.name}/gateways/create",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_create_gateway(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        backend = await create_backend(session, project.id, backend_type=BackendType.AWS)
        response = await client.post(
            f"/api/project/{project.name}/gateways/create",
            json={
                "configuration": {
                    "type": "gateway",
                    "name": "test",
                    "backend": "aws",
                    "region": "us",
                },
            },
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        assert response.json() == {
            "id": SomeUUID4Str(),
            "name": "test",
            "backend": "aws",
            "region": "us",
            "status": "submitted",
            "status_message": None,
            "instance_id": "",
            "ip_address": "",
            "hostname": "",
            "wildcard_domain": None,
            "default": True,
            "created_at": response.json()["created_at"],
            "configuration": {
                "type": "gateway",
                "name": "test",
                "backend": backend.type.value,
                "region": "us",
                "instance_type": None,
                "router": None,
                "domain": None,
                "default": True,
                "public_ip": True,
                "certificate": {"type": "lets-encrypt"},
                "tags": None,
            },
        }
        events = await list_events(session)
        assert events[0].message == "Gateway created. Status: SUBMITTED"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_create_gateway_without_name(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        backend = await create_backend(session, project.id, backend_type=BackendType.AWS)
        with patch("dstack._internal.server.services.gateways.random_names.generate_name") as g:
            g.return_value = "random-name"
            response = await client.post(
                f"/api/project/{project.name}/gateways/create",
                json={
                    "configuration": {
                        "type": "gateway",
                        "name": None,
                        "backend": "aws",
                        "region": "us",
                    },
                },
                headers=get_auth_headers(user.token),
            )
            g.assert_called_once()
        assert response.status_code == 200
        assert response.json() == {
            "id": SomeUUID4Str(),
            "name": "random-name",
            "backend": "aws",
            "region": "us",
            "status": "submitted",
            "status_message": None,
            "instance_id": "",
            "ip_address": "",
            "hostname": "",
            "wildcard_domain": None,
            "default": True,
            "created_at": response.json()["created_at"],
            "configuration": {
                "type": "gateway",
                "name": "random-name",
                "backend": backend.type.value,
                "region": "us",
                "instance_type": None,
                "router": None,
                "domain": None,
                "default": True,
                "public_ip": True,
                "certificate": {"type": "lets-encrypt"},
                "tags": None,
            },
        }
        events = await list_events(session)
        assert events[0].message == "Gateway created. Status: SUBMITTED"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_create_gateway_missing_backend(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        response = await client.post(
            f"/api/project/{project.name}/gateways/create",
            json={
                "configuration": {
                    "type": "gateway",
                    "name": "test",
                    "backend": "aws",
                    "region": "us",
                },
            },
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 400


class TestDefaultGateway:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_only_admin_can_set_default_gateway(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        backend = await create_backend(session, project.id)
        gateway = await create_gateway(session, project.id, backend.id)
        response = await client.post(
            f"/api/project/{project.name}/gateways/set_default",
            json={"name": gateway.name},
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_set_default_gateway(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        backend = await create_backend(session, project.id)
        gateway_compute = await create_gateway_compute(
            session=session,
            backend_id=backend.id,
        )
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            gateway_compute_id=gateway_compute.id,
            name="first_gateway",
        )
        response = await client.post(
            f"/api/project/{project.name}/gateways/set_default",
            json={"name": gateway.name},
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200

        response = await client.post(
            f"/api/project/{project.name}/gateways/get",
            json={"name": gateway.name},
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        assert response.json() == {
            "id": SomeUUID4Str(),
            "backend": backend.type.value,
            "created_at": response.json()["created_at"],
            "default": True,
            "status": "submitted",
            "status_message": None,
            "instance_id": gateway_compute.instance_id,
            "ip_address": gateway_compute.ip_address,
            "hostname": gateway_compute.ip_address,
            "name": gateway.name,
            "region": gateway.region,
            "wildcard_domain": gateway.wildcard_domain,
            "configuration": {
                "type": "gateway",
                "name": gateway.name,
                "backend": backend.type.value,
                "region": gateway.region,
                "instance_type": None,
                "router": None,
                "domain": gateway.wildcard_domain,
                "default": True,
                "public_ip": True,
                "certificate": {"type": "lets-encrypt"},
                "tags": None,
            },
        }
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Gateway set as default"

        second_gateway_compute = await create_gateway_compute(
            session=session,
            backend_id=backend.id,
        )
        second_gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            gateway_compute_id=second_gateway_compute.id,
            name="second_gateway",
        )
        await clear_events(session)
        response = await client.post(
            f"/api/project/{project.name}/gateways/set_default",
            json={"name": second_gateway.name},
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        events = await list_events(session)
        assert len(events) == 2
        actual_events = [(e.targets[0].entity_name, e.message) for e in events]
        expected_events = [
            ("first_gateway", "Gateway unset as default"),
            ("second_gateway", "Gateway set as default"),
        ]
        assert (
            actual_events == expected_events
            # in case events are emitted exactly at the same time
            or actual_events == expected_events[::-1]
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_set_default_gateway_missing(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        response = await client.post(
            f"/api/project/{project.name}/gateways/set_default",
            json={"name": "missing"},
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 400


class TestDeleteGateway:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_only_admin_can_delete(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = await client.post(
            f"/api/project/{project.name}/gateways/delete",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403


class TestDeleteGatewayPipelineEnabled:
    @pytest.fixture(autouse=True)
    def _pipeline_processing_enabled(self, patch_pipeline_processing_flag):
        patch_pipeline_processing_flag(True)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_marks_gateways_to_be_deleted(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        backend_aws = await create_backend(session, project.id)
        backend_gcp = await create_backend(session, project.id, backend_type=BackendType.GCP)
        gateway_compute_aws = await create_gateway_compute(
            session=session,
            backend_id=backend_aws.id,
        )
        gateway_aws = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend_aws.id,
            name="gateway-aws",
            gateway_compute_id=gateway_compute_aws.id,
        )
        gateway_compute_gcp = await create_gateway_compute(
            session=session,
            backend_id=backend_gcp.id,
        )
        gateway_gcp = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend_gcp.id,
            name="gateway-gcp",
            gateway_compute_id=gateway_compute_gcp.id,
        )
        response = await client.post(
            f"/api/project/{project.name}/gateways/delete",
            json={"names": [gateway_aws.name, gateway_gcp.name]},
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200

        await session.refresh(gateway_aws)
        await session.refresh(gateway_gcp)
        await session.refresh(gateway_compute_aws)
        await session.refresh(gateway_compute_gcp)
        assert gateway_aws.to_be_deleted is True
        assert gateway_gcp.to_be_deleted is True
        assert gateway_compute_aws.active is True
        assert gateway_compute_aws.deleted is False
        assert gateway_compute_gcp.active is True
        assert gateway_compute_gcp.deleted is False

        response = await client.post(
            f"/api/project/{project.name}/gateways/list",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        assert {g["name"] for g in response.json()} == {"gateway-aws", "gateway-gcp"}

        events = await list_events(session)
        assert len(events) == 2
        assert all(e.message == "Gateway marked for deletion" for e in events)
        assert {e.targets[0].entity_name for e in events} == {"gateway-aws", "gateway-gcp"}
        assert all(e.actor_user_id == user.id for e in events)


class TestDeleteGatewayPipelineDisabled:
    @pytest.fixture(autouse=True)
    def _pipeline_processing_disabled(self, patch_pipeline_processing_flag):
        patch_pipeline_processing_flag(False)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_deletes_gateways_synchronously(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        backend_aws = await create_backend(session, project.id)
        backend_gcp = await create_backend(session, project.id, backend_type=BackendType.GCP)
        gateway_compute_aws = await create_gateway_compute(
            session=session,
            backend_id=backend_aws.id,
        )
        gateway_aws = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend_aws.id,
            name="gateway-aws",
            gateway_compute_id=gateway_compute_aws.id,
        )
        gateway_compute_gcp = await create_gateway_compute(
            session=session,
            backend_id=backend_gcp.id,
        )
        gateway_gcp = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend_gcp.id,
            name="gateway-gcp",
            gateway_compute_id=gateway_compute_gcp.id,
        )
        with patch(
            "dstack._internal.server.services.gateways.get_project_backend_by_type_or_error"
        ) as m:
            aws = Mock()
            aws.compute.return_value = Mock(spec=ComputeMockSpec)
            aws.compute.return_value.terminate_gateway.return_value = None  # success
            gcp = Mock()
            gcp.compute.return_value = Mock(spec=ComputeMockSpec)
            gcp.compute.return_value.terminate_gateway.side_effect = DstackError()  # fail

            def get_backend(project, backend_type):
                return {BackendType.AWS: aws, BackendType.GCP: gcp}[backend_type]

            m.side_effect = get_backend

            response = await client.post(
                f"/api/project/{project.name}/gateways/delete",
                json={"names": [gateway_aws.name, gateway_gcp.name]},
                headers=get_auth_headers(user.token),
            )
            aws.compute.return_value.terminate_gateway.assert_called_once()
            gcp.compute.return_value.terminate_gateway.assert_called_once()
            assert response.status_code == 200

        response = await client.post(
            f"/api/project/{project.name}/gateways/list",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        assert response.json() == [
            {
                "id": str(gateway_gcp.id),
                "backend": backend_gcp.type.value,
                "created_at": response.json()[0]["created_at"],
                "default": False,
                "status": "submitted",
                "status_message": None,
                "instance_id": gateway_compute_gcp.instance_id,
                "ip_address": gateway_compute_gcp.ip_address,
                "hostname": gateway_compute_gcp.ip_address,
                "name": gateway_gcp.name,
                "region": gateway_gcp.region,
                "wildcard_domain": gateway_gcp.wildcard_domain,
                "configuration": {
                    "type": "gateway",
                    "name": gateway_gcp.name,
                    "backend": backend_gcp.type.value,
                    "region": gateway_gcp.region,
                    "instance_type": None,
                    "router": None,
                    "domain": gateway_gcp.wildcard_domain,
                    "default": False,
                    "public_ip": True,
                    "certificate": {"type": "lets-encrypt"},
                    "tags": None,
                },
            }
        ]

        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Gateway deleted"
        assert events[0].targets[0].entity_name == "gateway-aws"


class TestUpdateGateway:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_only_admin_can_set_wildcard_domain(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = await client.post(
            f"/api/project/{project.name}/gateways/set_wildcard_domain",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_set_wildcard_domain(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        backend = await create_backend(session, project.id)
        gateway_compute = await create_gateway_compute(
            session=session,
            backend_id=backend.id,
        )
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            gateway_compute_id=gateway_compute.id,
            wildcard_domain="old.example",
        )
        response = await client.post(
            f"/api/project/{project.name}/gateways/set_wildcard_domain",
            json={"name": gateway.name, "wildcard_domain": "new.example"},
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        assert response.json() == {
            "id": SomeUUID4Str(),
            "backend": backend.type.value,
            "created_at": response.json()["created_at"],
            "status": "submitted",
            "status_message": None,
            "default": False,
            "instance_id": gateway_compute.instance_id,
            "ip_address": gateway_compute.ip_address,
            "hostname": gateway_compute.ip_address,
            "name": gateway.name,
            "region": gateway.region,
            "wildcard_domain": "new.example",
            "configuration": {
                "type": "gateway",
                "name": gateway.name,
                "backend": backend.type.value,
                "region": gateway.region,
                "instance_type": None,
                "router": None,
                "domain": "new.example",
                "default": False,
                "public_ip": True,
                "certificate": {"type": "lets-encrypt"},
                "tags": None,
            },
        }
        events = await list_events(session)
        assert len(events) == 1
        assert (
            events[0].message == "Gateway wildcard domain changed 'old.example' -> 'new.example'"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_set_wildcard_domain_missing(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        response = await client.post(
            f"/api/project/{project.name}/gateways/set_wildcard_domain",
            json={"name": "missing", "wildcard_domain": "test.com"},
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 400
