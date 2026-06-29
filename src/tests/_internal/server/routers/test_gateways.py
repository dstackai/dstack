from typing import Any
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.testing.common import (
    clear_events,
    create_backend,
    create_export,
    create_gateway,
    create_gateway_compute,
    create_project,
    create_user,
    get_auth_headers,
    list_events,
)
from dstack._internal.server.testing.matchers import SomeUUID4Str


class TestListAndGetGateways:
    @pytest.mark.asyncio
    async def test_returns_40x_if_not_authenticated(self, client: AsyncClient):
        response = await client.post("/api/project/main/gateways/list")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @pytest.mark.parametrize("legacy_compute", [False, True])
    @pytest.mark.parametrize("populate_configuration", [True, False])
    async def test_list(
        self,
        test_db,
        session: AsyncSession,
        client: AsyncClient,
        legacy_compute: bool,
        populate_configuration: bool,
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            populate_configuration=populate_configuration,
        )
        if legacy_compute:
            gateway_compute = await create_gateway_compute(
                session=session,
                backend_id=backend.id,
                populate_configuration=populate_configuration,
            )
            gateway.gateway_compute_id = gateway_compute.id  # pre-0.20.25 relationship style
        else:
            gateway_compute = await create_gateway_compute(
                session=session,
                backend_id=backend.id,
                gateway_id=gateway.id,
                populate_configuration=populate_configuration,
            )
        await session.commit()
        response = await client.post(
            f"/api/project/{project.name}/gateways/list",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        assert response.json() == [
            {
                "id": SomeUUID4Str(),
                "project_name": project.name,
                "backend": backend.type.value,
                "created_at": response.json()[0]["created_at"],
                "default": False,
                "status": "submitted",
                "status_message": None,
                "replicas": [
                    {
                        "hostname": gateway_compute.ip_address,
                        "replica_num": 0,
                        "backend": backend.type.value,
                        "region": "us",
                        "created_at": response.json()[0]["replicas"][0]["created_at"],
                    }
                ],
                "instance_id": None,
                "ip_address": None,
                "hostname": None,
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
                    "replicas": None,
                },
            }
        ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @pytest.mark.parametrize("legacy_compute", [False, True])
    @pytest.mark.parametrize("populate_configuration", [True, False])
    async def test_get(
        self,
        test_db,
        session: AsyncSession,
        client: AsyncClient,
        legacy_compute: bool,
        populate_configuration: bool,
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        backend = await create_backend(session, project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            populate_configuration=populate_configuration,
        )
        if legacy_compute:
            gateway_compute = await create_gateway_compute(
                session=session,
                backend_id=backend.id,
                populate_configuration=populate_configuration,
            )
            gateway.gateway_compute_id = gateway_compute.id  # pre-0.20.25 relationship style
        else:
            gateway_compute = await create_gateway_compute(
                session=session,
                backend_id=backend.id,
                gateway_id=gateway.id,
                populate_configuration=populate_configuration,
            )
        await session.commit()
        response = await client.post(
            f"/api/project/{project.name}/gateways/get",
            json={"name": gateway.name},
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        assert response.json() == {
            "id": SomeUUID4Str(),
            "project_name": project.name,
            "backend": backend.type.value,
            "created_at": response.json()["created_at"],
            "default": False,
            "status": "submitted",
            "status_message": None,
            "replicas": [
                {
                    "hostname": gateway_compute.ip_address,
                    "replica_num": 0,
                    "backend": backend.type.value,
                    "region": "us",
                    "created_at": response.json()["replicas"][0]["created_at"],
                }
            ],
            "instance_id": None,
            "ip_address": None,
            "hostname": None,
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
                "replicas": None,
            },
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_list_legacy_client_populates_compat_fields(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        """Old clients (< 0.20.25) get ip_address/instance_id/hostname back-filled."""
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
        )
        gateway_compute = await create_gateway_compute(
            session=session,
            backend_id=backend.id,
            gateway_id=gateway.id,
        )
        response = await client.post(
            f"/api/project/{project.name}/gateways/list",
            headers={**get_auth_headers(user.token), "x-api-version": "0.20.24"},
        )
        assert response.status_code == 200
        assert len(response.json()) == 1
        gw = response.json()[0]
        assert gw["ip_address"] == gateway_compute.ip_address
        assert gw["instance_id"] == ""
        assert gw["hostname"] == gateway_compute.ip_address

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_list_non_member_public_project(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session, is_public=True)
        backend = await create_backend(session=session, project_id=project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
        )
        await create_gateway_compute(
            session=session,
            backend_id=backend.id,
            gateway_id=gateway.id,
        )
        response = await client.post(
            f"/api/project/{project.name}/gateways/list",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["name"] == gateway.name

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_get_non_member_public_project(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session, is_public=True)
        backend = await create_backend(session, project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
        )
        await create_gateway_compute(
            session=session,
            backend_id=backend.id,
            gateway_id=gateway.id,
        )
        response = await client.post(
            f"/api/project/{project.name}/gateways/get",
            json={"name": gateway.name},
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        assert response.json()["name"] == gateway.name

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

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_list_returns_imported_gateway_with_include_imported(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        importer_user = await create_user(
            session, name="importer-user", global_role=GlobalRole.USER
        )
        exporter_project = await create_project(session, name="exporter-project")
        importer_project = await create_project(
            session, name="importer-project", owner=importer_user
        )
        await add_project_member(
            session=session,
            project=importer_project,
            user=importer_user,
            project_role=ProjectRole.ADMIN,
        )
        backend = await create_backend(session=session, project_id=exporter_project.id)
        gateway = await create_gateway(
            session=session,
            project_id=exporter_project.id,
            backend_id=backend.id,
            name="exported-gateway",
        )
        await create_gateway_compute(session=session, backend_id=backend.id, gateway_id=gateway.id)
        await create_export(
            session=session,
            exporter_project=exporter_project,
            importer_projects=[importer_project],
            exported_fleets=[],
            exported_gateways=[gateway],
        )
        response = await client.post(
            f"/api/project/{importer_project.name}/gateways/list",
            headers=get_auth_headers(importer_user.token),
            json={"include_imported": True},
        )
        assert response.status_code == 200
        response_json = response.json()
        assert len(response_json) == 1
        assert response_json[0]["name"] == "exported-gateway"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_list_not_returns_imported_gateway_without_include_imported(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        importer_user = await create_user(
            session, name="importer-user", global_role=GlobalRole.USER
        )
        exporter_project = await create_project(session, name="exporter-project")
        importer_project = await create_project(
            session, name="importer-project", owner=importer_user
        )
        await add_project_member(
            session=session,
            project=importer_project,
            user=importer_user,
            project_role=ProjectRole.ADMIN,
        )
        backend = await create_backend(session=session, project_id=exporter_project.id)
        gateway = await create_gateway(
            session=session,
            project_id=exporter_project.id,
            backend_id=backend.id,
            name="exported-gateway",
        )
        await create_gateway_compute(session=session, backend_id=backend.id, gateway_id=gateway.id)
        await create_export(
            session=session,
            exporter_project=exporter_project,
            importer_projects=[importer_project],
            exported_fleets=[],
            exported_gateways=[gateway],
        )
        response = await client.post(
            f"/api/project/{importer_project.name}/gateways/list",
            headers=get_auth_headers(importer_user.token),
            json={},
        )
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_get_returns_imported_gateway(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        importer_user = await create_user(
            session, name="importer-user", global_role=GlobalRole.USER
        )
        exporter_project = await create_project(session, name="exporter-project")
        importer_project = await create_project(
            session, name="importer-project", owner=importer_user
        )
        await add_project_member(
            session=session,
            project=importer_project,
            user=importer_user,
            project_role=ProjectRole.ADMIN,
        )
        backend = await create_backend(session=session, project_id=exporter_project.id)
        gateway = await create_gateway(
            session=session,
            project_id=exporter_project.id,
            backend_id=backend.id,
            name="exported-gateway",
        )
        await create_gateway_compute(session=session, backend_id=backend.id, gateway_id=gateway.id)
        await create_export(
            session=session,
            exporter_project=exporter_project,
            importer_projects=[importer_project],
            exported_fleets=[],
            exported_gateways=[gateway],
        )
        response = await client.post(
            f"/api/project/{exporter_project.name}/gateways/get",
            headers=get_auth_headers(importer_user.token),
            json={"name": "exported-gateway"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "exported-gateway"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_get_returns_403_on_foreign_gateway_if_not_imported(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        importer_user = await create_user(
            session, name="importer-user", global_role=GlobalRole.USER
        )
        not_importer_user = await create_user(
            session, name="not-importer-user", global_role=GlobalRole.USER
        )
        exporter_project = await create_project(session, name="exporter-project")
        importer_project = await create_project(
            session, name="importer-project", owner=importer_user
        )
        not_importer_project = await create_project(
            session, name="not-importer-project", owner=not_importer_user
        )
        await add_project_member(
            session=session,
            project=not_importer_project,
            user=not_importer_user,
            project_role=ProjectRole.USER,
        )
        backend = await create_backend(session=session, project_id=exporter_project.id)
        gateway = await create_gateway(
            session=session,
            project_id=exporter_project.id,
            backend_id=backend.id,
            name="exported-gateway",
        )
        await create_gateway_compute(session=session, backend_id=backend.id, gateway_id=gateway.id)
        await create_export(
            session=session,
            exporter_project=exporter_project,
            importer_projects=[importer_project],
            exported_fleets=[],
            exported_gateways=[gateway],
        )
        response = await client.post(
            f"/api/project/{exporter_project.name}/gateways/get",
            headers=get_auth_headers(not_importer_user.token),
            json={"name": "exported-gateway"},
        )
        assert response.status_code == 403


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
            "project_name": project.name,
            "name": "test",
            "backend": "aws",
            "region": "us",
            "status": "submitted",
            "status_message": None,
            "replicas": [],
            "instance_id": None,
            "ip_address": None,
            "hostname": None,
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
                "replicas": None,
            },
        }
        events = await list_events(session)
        assert events[0].message == "Gateway created. Status: SUBMITTED"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_create_multi_replica_gateway(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        await create_backend(session, project.id, backend_type=BackendType.AWS)
        response = await client.post(
            f"/api/project/{project.name}/gateways/create",
            json={
                "configuration": {
                    "type": "gateway",
                    "name": "test",
                    "backend": "aws",
                    "region": "us",
                    "replicas": 2,
                    "certificate": None,
                },
            },
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        assert response.json()["configuration"]["replicas"] == 2
        assert response.json()["replicas"] == []  # populated later by pipelines
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
            "project_name": project.name,
            "name": "random-name",
            "backend": "aws",
            "region": "us",
            "status": "submitted",
            "status_message": None,
            "replicas": [],
            "instance_id": None,
            "ip_address": None,
            "hostname": None,
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
                "replicas": None,
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

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_create_gateway_with_valid_domain_interpolation(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        await create_backend(session, project.id, backend_type=BackendType.AWS)
        response = await client.post(
            f"/api/project/{project.name}/gateways/create",
            json={
                "configuration": {
                    "type": "gateway",
                    "name": "test",
                    "backend": "aws",
                    "region": "us",
                    "domain": "${{ run.project_name }}.example.com",
                },
            },
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_create_gateway_with_invalid_domain_interpolation(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        await create_backend(session, project.id, backend_type=BackendType.AWS)
        response = await client.post(
            f"/api/project/{project.name}/gateways/create",
            json={
                "configuration": {
                    "type": "gateway",
                    "name": "test",
                    "backend": "aws",
                    "region": "us",
                    "domain": "${{ run.unknown_variable }}.example.com",
                },
            },
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @pytest.mark.parametrize(
        "configuration, expected_error",
        [
            pytest.param(
                {
                    "type": "gateway",
                    "name": "test",
                    "backend": "aws",
                    "region": "us",
                    "domain": "${{ run.unknown_variable }}.example.com",
                },
                "Cannot interpolate gateway domain name: Failed to interpolate due to missing vars: ['run.unknown_variable']",
                id="invalid-domain-interpolation",
            ),
            pytest.param(
                {
                    "type": "gateway",
                    "name": "test",
                    "backend": "aws",
                    "region": "us",
                    "certificate": {
                        "type": "acm",
                        "arn": "arn:aws:acm:us-east-1:123456789:certificate/abc",
                    },
                    "replicas": 2,
                },
                "Replicated gateways do not support certificates."
                " Set either `certificate: null` or `replicas: 1` in the gateway configuration",
                id="multi-replica-with-acm-cert",
            ),
            pytest.param(
                {
                    "type": "gateway",
                    "name": "test",
                    "backend": "aws",
                    "region": "us",
                    "certificate": {"type": "lets-encrypt"},
                    "replicas": 2,
                },
                "Replicated gateways do not support certificates."
                " Set either `certificate: null` or `replicas: 1` in the gateway configuration",
                id="multi-replica-with-letsencrypt-cert",
            ),
            pytest.param(
                {
                    "type": "gateway",
                    "name": "test",
                    "backend": "aws",
                    "region": "us",
                    "certificate": None,
                    "router": {"type": "sglang"},
                    "replicas": 2,
                },
                "The deprecated `router` property is not supported for multi-replica gateways",
                id="multi-replica-with-router",
            ),
            pytest.param(
                {
                    "type": "gateway",
                    "name": "test",
                    "backend": "aws",
                    "region": "us",
                    "certificate": None,
                    "replicas": 4,
                },
                "Cannot provision 4 gateway replicas. This server allows at most 3",
                id="replicas-exceed-max",
            ),
        ],
    )
    async def test_invalid_configuration_rejected(
        self,
        test_db,
        session: AsyncSession,
        client: AsyncClient,
        configuration: dict[str, Any],
        expected_error: str,
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        await create_backend(session, project.id, backend_type=BackendType.AWS)
        response = await client.post(
            f"/api/project/{project.name}/gateways/create",
            json={"configuration": configuration},
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 400
        assert response.json()["detail"][0]["msg"] == expected_error


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
    @pytest.mark.parametrize("populate_configuration", [True, False])
    async def test_set_default_gateway(
        self, test_db, session: AsyncSession, client: AsyncClient, populate_configuration: bool
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        backend = await create_backend(session, project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            name="first_gateway",
            populate_configuration=populate_configuration,
        )
        gateway_compute = await create_gateway_compute(
            session=session,
            backend_id=backend.id,
            gateway_id=gateway.id,
            populate_configuration=populate_configuration,
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
            "project_name": project.name,
            "backend": backend.type.value,
            "created_at": response.json()["created_at"],
            "default": True,
            "status": "submitted",
            "status_message": None,
            "replicas": [
                {
                    "hostname": gateway_compute.ip_address,
                    "replica_num": 0,
                    "backend": backend.type.value,
                    "region": "us",
                    "created_at": response.json()["replicas"][0]["created_at"],
                }
            ],
            "instance_id": None,
            "ip_address": None,
            "hostname": None,
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
                "replicas": None,
            },
        }
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Gateway set as project default"

        second_gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            name="second_gateway",
            populate_configuration=populate_configuration,
        )
        await create_gateway_compute(
            session=session,
            backend_id=backend.id,
            gateway_id=second_gateway.id,
            populate_configuration=populate_configuration,
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
        actual_events = [({t.entity_name for t in e.targets}, e.message) for e in events]
        expected_events = [
            ({"first_gateway", project.name}, "Gateway unset as project default"),
            ({"second_gateway", project.name}, "Gateway set as project default"),
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

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_importer_member_cannot_set_default_imported_gateway(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        importer_user = await create_user(
            session, name="importer-user", global_role=GlobalRole.USER
        )
        exporter_project = await create_project(session, name="exporter-project")
        importer_project = await create_project(
            session, name="importer-project", owner=importer_user
        )
        await add_project_member(
            session=session,
            project=importer_project,
            user=importer_user,
            project_role=ProjectRole.ADMIN,
        )
        backend = await create_backend(session=session, project_id=exporter_project.id)
        gateway = await create_gateway(
            session=session,
            project_id=exporter_project.id,
            backend_id=backend.id,
            name="exported-gateway",
        )
        await create_export(
            session=session,
            exporter_project=exporter_project,
            importer_projects=[importer_project],
            exported_fleets=[],
            exported_gateways=[gateway],
        )
        response = await client.post(
            f"/api/project/{exporter_project.name}/gateways/set_default",
            headers=get_auth_headers(importer_user.token),
            json={"name": gateway.name},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_set_imported_gateway_as_default(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        importer_user = await create_user(
            session, name="importer-user", global_role=GlobalRole.USER
        )
        exporter_project = await create_project(session, name="exporter-project")
        importer_project = await create_project(
            session, name="importer-project", owner=importer_user
        )
        await add_project_member(
            session=session,
            project=importer_project,
            user=importer_user,
            project_role=ProjectRole.ADMIN,
        )
        backend = await create_backend(session=session, project_id=exporter_project.id)
        gateway = await create_gateway(
            session=session,
            project_id=exporter_project.id,
            backend_id=backend.id,
            name="exported-gateway",
        )
        await create_gateway_compute(session=session, backend_id=backend.id, gateway_id=gateway.id)
        await create_export(
            session=session,
            exporter_project=exporter_project,
            importer_projects=[importer_project],
            exported_fleets=[],
            exported_gateways=[gateway],
        )
        response = await client.post(
            f"/api/project/{importer_project.name}/gateways/set_default",
            headers=get_auth_headers(importer_user.token),
            json={"name": gateway.name, "gateway_project": exporter_project.name},
        )
        assert response.status_code == 200
        await session.refresh(importer_project)
        assert importer_project.default_gateway_id == gateway.id
        events = await list_events(session)
        assert any(e.message == "Gateway set as project default" for e in events)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_cannot_set_non_imported_foreign_gateway_as_default(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        not_importer_user = await create_user(
            session, name="not-importer-user", global_role=GlobalRole.USER
        )
        exporter_project = await create_project(session, name="exporter-project")
        not_importer_project = await create_project(
            session, name="not-importer-project", owner=not_importer_user
        )
        await add_project_member(
            session=session,
            project=not_importer_project,
            user=not_importer_user,
            project_role=ProjectRole.ADMIN,
        )
        backend = await create_backend(session=session, project_id=exporter_project.id)
        gateway = await create_gateway(
            session=session,
            project_id=exporter_project.id,
            backend_id=backend.id,
            name="exported-gateway",
        )
        await create_gateway_compute(session=session, backend_id=backend.id, gateway_id=gateway.id)
        await create_export(
            session=session,
            exporter_project=exporter_project,
            importer_projects=[],
            exported_fleets=[],
            exported_gateways=[gateway],
        )
        response = await client.post(
            f"/api/project/{not_importer_project.name}/gateways/set_default",
            headers=get_auth_headers(not_importer_user.token),
            json={"name": gateway.name, "gateway_project": exporter_project.name},
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

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @pytest.mark.parametrize("populate_configuration", [True, False])
    async def test_marks_gateways_to_be_deleted(
        self,
        test_db,
        session: AsyncSession,
        client: AsyncClient,
        populate_configuration: bool,
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        backend_aws = await create_backend(session, project.id)
        backend_gcp = await create_backend(session, project.id, backend_type=BackendType.GCP)
        gateway_aws = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend_aws.id,
            name="gateway-aws",
            populate_configuration=populate_configuration,
        )
        gateway_compute_aws = await create_gateway_compute(
            session=session,
            backend_id=backend_aws.id,
            gateway_id=gateway_aws.id,
            populate_configuration=populate_configuration,
        )
        gateway_gcp = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend_gcp.id,
            name="gateway-gcp",
            populate_configuration=populate_configuration,
        )
        gateway_compute_gcp = await create_gateway_compute(
            session=session,
            backend_id=backend_gcp.id,
            gateway_id=gateway_gcp.id,
            populate_configuration=populate_configuration,
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

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_importer_member_cannot_delete_imported_gateway(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        importer_user = await create_user(
            session, name="importer-user", global_role=GlobalRole.USER
        )
        exporter_project = await create_project(session, name="exporter-project")
        importer_project = await create_project(
            session, name="importer-project", owner=importer_user
        )
        await add_project_member(
            session=session,
            project=importer_project,
            user=importer_user,
            project_role=ProjectRole.ADMIN,
        )
        backend = await create_backend(session=session, project_id=exporter_project.id)
        gateway = await create_gateway(
            session=session,
            project_id=exporter_project.id,
            backend_id=backend.id,
            name="exported-gateway",
        )
        await create_export(
            session=session,
            exporter_project=exporter_project,
            importer_projects=[importer_project],
            exported_fleets=[],
            exported_gateways=[gateway],
        )
        response = await client.post(
            f"/api/project/{exporter_project.name}/gateways/delete",
            headers=get_auth_headers(importer_user.token),
            json={"names": [gateway.name]},
        )
        assert response.status_code == 403


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
    @pytest.mark.parametrize("populate_configuration", [True, False])
    async def test_set_wildcard_domain(
        self, test_db, session: AsyncSession, client: AsyncClient, populate_configuration: bool
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        backend = await create_backend(session, project.id)
        gateway = await create_gateway(
            session=session,
            project_id=project.id,
            backend_id=backend.id,
            wildcard_domain="old.example",
            populate_configuration=populate_configuration,
        )
        gateway_compute = await create_gateway_compute(
            session=session,
            backend_id=backend.id,
            gateway_id=gateway.id,
            populate_configuration=populate_configuration,
        )
        response = await client.post(
            f"/api/project/{project.name}/gateways/set_wildcard_domain",
            json={"name": gateway.name, "wildcard_domain": "new.example"},
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        assert response.json() == {
            "id": SomeUUID4Str(),
            "project_name": project.name,
            "backend": backend.type.value,
            "created_at": response.json()["created_at"],
            "status": "submitted",
            "status_message": None,
            "default": False,
            "replicas": [
                {
                    "hostname": gateway_compute.ip_address,
                    "replica_num": 0,
                    "backend": backend.type.value,
                    "region": "us",
                    "created_at": response.json()["replicas"][0]["created_at"],
                }
            ],
            "instance_id": None,
            "ip_address": None,
            "hostname": None,
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
                "replicas": None,
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

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_importer_member_cannot_set_wildcard_domain_on_imported_gateway(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        importer_user = await create_user(
            session, name="importer-user", global_role=GlobalRole.USER
        )
        exporter_project = await create_project(session, name="exporter-project")
        importer_project = await create_project(
            session, name="importer-project", owner=importer_user
        )
        await add_project_member(
            session=session,
            project=importer_project,
            user=importer_user,
            project_role=ProjectRole.ADMIN,
        )
        backend = await create_backend(session=session, project_id=exporter_project.id)
        gateway = await create_gateway(
            session=session,
            project_id=exporter_project.id,
            backend_id=backend.id,
            name="exported-gateway",
        )
        await create_export(
            session=session,
            exporter_project=exporter_project,
            importer_projects=[importer_project],
            exported_fleets=[],
            exported_gateways=[gateway],
        )
        response = await client.post(
            f"/api/project/{exporter_project.name}/gateways/set_wildcard_domain",
            headers=get_auth_headers(importer_user.token),
            json={"name": gateway.name, "wildcard_domain": "new.example"},
        )
        assert response.status_code == 403
