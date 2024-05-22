from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import DstackError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.main import app
from dstack._internal.server.services.gateways import (
    gateway_model_to_gateway,
    get_project_default_gateway,
)
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.testing.common import (
    create_backend,
    create_gateway,
    create_gateway_compute,
    create_project,
    create_user,
    get_auth_headers,
)

client = TestClient(app)


class TestListAndGetGateways:
    @pytest.mark.asyncio
    async def test_returns_40x_if_not_authenticated(self, test_db, session: AsyncSession):
        response = client.post("/api/project/main/gateways/list")
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_list(self, test_db, session: AsyncSession):
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
        response = client.post(
            f"/api/project/{project.name}/gateways/list",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        assert response.json() == [
            {
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
                    "domain": gateway.wildcard_domain,
                    "default": False,
                    "public_ip": True,
                    "certificate": {"type": "lets-encrypt"},
                },
            }
        ]

    @pytest.mark.asyncio
    async def test_get(self, test_db, session: AsyncSession):
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
        response = client.post(
            f"/api/project/{project.name}/gateways/get",
            json={"name": gateway.name},
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        assert response.json() == {
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
                "domain": gateway.wildcard_domain,
                "default": False,
                "public_ip": True,
                "certificate": {"type": "lets-encrypt"},
            },
        }

    @pytest.mark.asyncio
    async def test_get_missing(self, test_db, session: AsyncSession):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = client.post(
            f"/api/project/{project.name}/gateways/get",
            json={"name": "missing"},
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 400


class TestCreateGateway:
    @pytest.mark.asyncio
    async def test_only_admin_can_create(self, test_db, session: AsyncSession):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = client.post(
            f"/api/project/{project.name}/gateways/create",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_gateway(self, test_db, session: AsyncSession):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        backend = await create_backend(session, project.id, backend_type=BackendType.AWS)
        response = client.post(
            f"/api/project/{project.name}/gateways/create",
            json={"name": "test", "backend_type": "aws", "region": "us"},
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        assert response.json() == {
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
                "domain": None,
                "default": True,
                "public_ip": True,
                "certificate": {"type": "lets-encrypt"},
            },
        }

    @pytest.mark.asyncio
    async def test_create_gateway_without_name(self, test_db, session: AsyncSession):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        backend = await create_backend(session, project.id, backend_type=BackendType.AWS)
        with patch("dstack._internal.server.services.gateways.random_names.generate_name") as g:
            g.return_value = "random-name"
            response = client.post(
                f"/api/project/{project.name}/gateways/create",
                json={"name": None, "backend_type": "aws", "region": "us"},
                headers=get_auth_headers(user.token),
            )
            g.assert_called_once()
        assert response.status_code == 200
        assert response.json() == {
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
                "domain": None,
                "default": True,
                "public_ip": True,
                "certificate": {"type": "lets-encrypt"},
            },
        }

    @pytest.mark.asyncio
    async def test_create_gateway_missing_backend(self, test_db, session: AsyncSession):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        response = client.post(
            f"/api/project/{project.name}/gateways/create",
            json={"name": "test", "backend_type": "aws", "region": "us"},
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 400


class TestDefaultGateway:
    @pytest.mark.asyncio
    async def test_get_default_gateway(self, test_db, session: AsyncSession):
        project = await create_project(session)
        backend = await create_backend(session, project.id)
        gateway = await create_gateway(session, project.id, backend.id)
        async with session.begin():
            project.default_gateway_id = gateway.id
            session.add(project)

        res = await get_project_default_gateway(session, project)
        assert res is not None
        assert res.dict() == gateway_model_to_gateway(gateway).dict()

    @pytest.mark.asyncio
    async def test_default_gateway_is_missing(self, test_db, session: AsyncSession):
        project = await create_project(session)
        backend = await create_backend(session, project.id)
        await create_gateway(session, project.id, backend.id)

        res = await get_project_default_gateway(session, project)
        assert res is None

    @pytest.mark.asyncio
    async def test_only_admin_can_set_default_gateway(self, test_db, session: AsyncSession):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        backend = await create_backend(session, project.id)
        gateway = await create_gateway(session, project.id, backend.id)
        response = client.post(
            f"/api/project/{project.name}/gateways/set_default",
            json={"name": gateway.name},
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_set_default_gateway(self, test_db, session: AsyncSession):
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
        )
        response = client.post(
            f"/api/project/{project.name}/gateways/set_default",
            json={"name": gateway.name},
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200

        response = client.post(
            f"/api/project/{project.name}/gateways/get",
            json={"name": gateway.name},
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        assert response.json() == {
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
                "domain": gateway.wildcard_domain,
                "default": True,
                "public_ip": True,
                "certificate": {"type": "lets-encrypt"},
            },
        }

    @pytest.mark.asyncio
    async def test_set_default_gateway_missing(self, test_db, session: AsyncSession):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        response = client.post(
            f"/api/project/{project.name}/gateways/set_default",
            json={"name": "missing"},
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 400


class TestDeleteGateway:
    @pytest.mark.asyncio
    async def test_only_admin_can_delete(self, test_db, session: AsyncSession):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = client.post(
            f"/api/project/{project.name}/gateways/delete",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_gateway(self, test_db, session: AsyncSession):
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
            aws.compute.return_value.terminate_gateway.return_value = None  # success
            gcp = Mock()
            gcp.compute.return_value.terminate_gateway.side_effect = DstackError()  # fail

            def get_backend(_, backend_type):
                return {BackendType.AWS: aws, BackendType.GCP: gcp}[backend_type]

            m.side_effect = get_backend

            response = client.post(
                f"/api/project/{project.name}/gateways/delete",
                json={"names": [gateway_aws.name, gateway_gcp.name]},
                headers=get_auth_headers(user.token),
            )
            aws.compute.return_value.terminate_gateway.assert_called_once()
            gcp.compute.return_value.terminate_gateway.assert_called_once()
            assert response.status_code == 200

        response = client.post(
            f"/api/project/{project.name}/gateways/list",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        assert response.json() == [
            {
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
                    "domain": gateway_gcp.wildcard_domain,
                    "default": False,
                    "public_ip": True,
                    "certificate": {"type": "lets-encrypt"},
                },
            }
        ]


class TestUpdateGateway:
    @pytest.mark.asyncio
    async def test_only_admin_can_set_wildcard_domain(self, test_db, session: AsyncSession):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = client.post(
            f"/api/project/{project.name}/gateways/set_wildcard_domain",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_set_wildcard_domain(self, test_db, session: AsyncSession):
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
        )
        response = client.post(
            f"/api/project/{project.name}/gateways/set_wildcard_domain",
            json={"name": gateway.name, "wildcard_domain": "test.com"},
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        assert response.json() == {
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
            "wildcard_domain": "test.com",
            "configuration": {
                "type": "gateway",
                "name": gateway.name,
                "backend": backend.type.value,
                "region": gateway.region,
                "domain": "test.com",
                "default": False,
                "public_ip": True,
                "certificate": {"type": "lets-encrypt"},
            },
        }

    @pytest.mark.asyncio
    async def test_set_wildcard_domain_missing(self, test_db, session: AsyncSession):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        response = client.post(
            f"/api/project/{project.name}/gateways/set_wildcard_domain",
            json={"name": "missing", "wildcard_domain": "test.com"},
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 400
