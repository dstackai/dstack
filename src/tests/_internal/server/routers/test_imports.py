from typing import Optional

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.models import ExportModel, ImportModel
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.testing.common import (
    create_backend,
    create_export,
    create_fleet,
    create_gateway,
    create_project,
    create_user,
    get_auth_headers,
    get_fleet_spec,
    get_ssh_fleet_configuration,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.usefixtures("test_db"),
    pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True),
]


class TestDeleteImport:
    async def test_returns_403_if_not_authenticated(self, client: AsyncClient):
        response = await client.post(
            "/api/project/TestProject/imports/delete",
            json={"export_name": "test-export", "export_project_name": "ExporterProject"},
        )
        assert response.status_code in [401, 403]

    async def test_returns_403_if_not_admin(self, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        exporter_project = await create_project(
            session=session, name="ExporterProject", owner=user
        )
        importer_project = await create_project(
            session=session, name="ImporterProject", owner=user
        )
        # The user is admin of the exporter project, but not of the importer
        await add_project_member(
            session=session, project=exporter_project, user=user, project_role=ProjectRole.ADMIN
        )
        await add_project_member(
            session=session, project=importer_project, user=user, project_role=ProjectRole.USER
        )
        response = await client.post(
            f"/api/project/{importer_project.name}/imports/delete",
            headers=get_auth_headers(user.token),
            json={"export_name": "test-export", "export_project_name": "ExporterProject"},
        )
        assert response.status_code == 403

    async def test_deletes_import(self, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        importer_project = await create_project(
            session=session, name="ImporterProject", owner=user
        )
        await add_project_member(
            session=session, project=importer_project, user=user, project_role=ProjectRole.ADMIN
        )
        exporter_project = await create_project(session=session, name="ExporterProject")
        fleet = await create_fleet(
            session=session,
            project=exporter_project,
            name="fleet1",
            spec=get_fleet_spec(get_ssh_fleet_configuration()),
        )
        await create_export(
            session=session,
            exporter_project=exporter_project,
            importer_projects=[importer_project],
            exported_fleets=[fleet],
            name="test-export",
        )

        response = await client.post(
            f"/api/project/{importer_project.name}/imports/delete",
            headers=get_auth_headers(user.token),
            json={
                "export_name": "test-export",
                "export_project_name": "ExPoRtErPrOjEcT",  # case-insensitive
            },
        )
        assert response.status_code == 200

        res = await session.execute(select(func.count()).select_from(ImportModel))
        assert res.scalar_one() == 0
        res = await session.execute(select(func.count()).select_from(ExportModel))
        assert res.scalar_one() == 1

    async def test_returns_400_for_nonexistent_import(
        self, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        importer_project = await create_project(
            session=session, name="ImporterProject", owner=user
        )
        await add_project_member(
            session=session, project=importer_project, user=user, project_role=ProjectRole.ADMIN
        )

        exporter_project = await create_project(
            session=session, name="ExporterProject", owner=user
        )
        await create_export(
            session=session,
            exporter_project=exporter_project,
            importer_projects=[],
            exported_fleets=[],
            name="test-export",
        )

        async def assert_not_found(export_project_name, export_name):
            response = await client.post(
                f"/api/project/{importer_project.name}/imports/delete",
                headers=get_auth_headers(user.token),
                json={"export_name": export_name, "export_project_name": export_project_name},
            )
            assert response.status_code == 400
            assert response.json()["detail"][0]["code"] == "resource_not_exists"
            # The error should be the same regardless of what wasn't found
            # (the exporter, the export, or the import),
            # so that users cannot infer the existence of exports they are not given access to.
            assert response.json()["detail"][0]["msg"] == (
                f"Import '{export_project_name}/{export_name}' not found in project 'ImporterProject'"
            )

        # Exporter not found
        await assert_not_found(export_project_name="WrongProject", export_name="test-export")
        # Export not found
        await assert_not_found(export_project_name="ExporterProject", export_name="wrong-export")
        # Import not found
        await assert_not_found(export_project_name="ExporterProject", export_name="test-export")


class TestListImports:
    async def test_returns_403_if_not_authenticated(self, client: AsyncClient):
        response = await client.post(
            "/api/project/TestProject/imports/list",
        )
        assert response.status_code in [401, 403]

    async def test_returns_403_if_not_member(self, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        response = await client.post(
            f"/api/project/{project.name}/imports/list",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 403

    @pytest.mark.parametrize(
        "global_role, project_role",
        [
            (GlobalRole.ADMIN, None),
            (GlobalRole.USER, ProjectRole.USER),
        ],
    )
    async def test_lists_imports(
        self,
        session: AsyncSession,
        client: AsyncClient,
        global_role: GlobalRole,
        project_role: Optional[ProjectRole],
    ):
        user = await create_user(session=session, global_role=global_role)
        importer_project = await create_project(
            session=session, name="ImporterProject", owner=user
        )
        if project_role:
            await add_project_member(
                session=session, project=importer_project, user=user, project_role=project_role
            )

        exporter_project1 = await create_project(
            session=session, name="ExporterProject1", owner=user
        )
        exporter_project2 = await create_project(
            session=session, name="ExporterProject2", owner=user
        )
        fleet1 = await create_fleet(
            session=session,
            project=exporter_project1,
            name="fleet1",
            spec=get_fleet_spec(get_ssh_fleet_configuration()),
        )
        fleet2 = await create_fleet(
            session=session,
            project=exporter_project2,
            name="fleet2",
            spec=get_fleet_spec(get_ssh_fleet_configuration()),
        )
        backend1 = await create_backend(session=session, project_id=exporter_project1.id)
        gateway1 = await create_gateway(
            session=session,
            project_id=exporter_project1.id,
            backend_id=backend1.id,
            name="gateway1",
        )
        backend2 = await create_backend(session=session, project_id=exporter_project2.id)
        gateway2 = await create_gateway(
            session=session,
            project_id=exporter_project2.id,
            backend_id=backend2.id,
            name="gateway2",
        )
        await create_export(
            session=session,
            exporter_project=exporter_project1,
            importer_projects=[importer_project],
            exported_fleets=[fleet1],
            exported_gateways=[gateway1],
            name="export1",
        )
        await create_export(
            session=session,
            exporter_project=exporter_project2,
            importer_projects=[importer_project],
            exported_fleets=[fleet2],
            exported_gateways=[gateway2],
            name="export2",
        )

        response = await client.post(
            f"/api/project/{importer_project.name}/imports/list",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        imports = response.json()
        assert len(imports) == 2
        imports.sort(key=lambda i: i["export"]["name"])

        assert imports[0]["export"]["name"] == "export1"
        assert imports[0]["export"]["project_name"] == "ExporterProject1"
        assert len(imports[0]["export"]["exported_fleets"]) == 1
        assert imports[0]["export"]["exported_fleets"][0]["name"] == "fleet1"
        assert len(imports[0]["export"]["exported_gateways"]) == 1
        assert imports[0]["export"]["exported_gateways"][0]["name"] == "gateway1"

        assert imports[1]["export"]["name"] == "export2"
        assert imports[1]["export"]["project_name"] == "ExporterProject2"
        assert len(imports[1]["export"]["exported_fleets"]) == 1
        assert imports[1]["export"]["exported_fleets"][0]["name"] == "fleet2"
        assert len(imports[1]["export"]["exported_gateways"]) == 1
        assert imports[1]["export"]["exported_gateways"][0]["name"] == "gateway2"

    @pytest.mark.parametrize(
        "global_role, project_role",
        [
            (GlobalRole.ADMIN, None),
            (GlobalRole.USER, ProjectRole.USER),
        ],
    )
    async def test_returns_empty_list_when_no_imports(
        self,
        session: AsyncSession,
        client: AsyncClient,
        global_role: GlobalRole,
        project_role: Optional[ProjectRole],
    ):
        user = await create_user(session=session, global_role=global_role)
        project = await create_project(session=session, owner=user)
        if project_role:
            await add_project_member(
                session=session, project=project, user=user, project_role=project_role
            )

        response = await client.post(
            f"/api/project/{project.name}/imports/list",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        assert response.json() == []

    async def test_not_includes_deleted_fleets(self, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        importer_project = await create_project(
            session=session, name="ImporterProject", owner=user
        )
        await add_project_member(
            session=session, project=importer_project, user=user, project_role=ProjectRole.USER
        )
        exporter_project = await create_project(
            session=session, name="ExporterProject", owner=user
        )

        fleet = await create_fleet(
            session=session,
            project=exporter_project,
            name="fleet",
            spec=get_fleet_spec(get_ssh_fleet_configuration()),
        )
        deleted_fleet = await create_fleet(
            session=session,
            project=exporter_project,
            name="deleted-fleet",
            spec=get_fleet_spec(get_ssh_fleet_configuration()),
            deleted=True,
        )
        await create_export(
            session=session,
            exporter_project=exporter_project,
            importer_projects=[importer_project],
            exported_fleets=[fleet, deleted_fleet],
            name="test-export",
        )

        response = await client.post(
            f"/api/project/{importer_project.name}/imports/list",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        imports = response.json()
        assert len(imports) == 1
        assert imports[0]["export"]["name"] == "test-export"
        assert len(imports[0]["export"]["exported_fleets"]) == 1
        assert imports[0]["export"]["exported_fleets"][0]["name"] == "fleet"

    async def test_does_not_include_other_projects_imports(
        self, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        other_project = await create_project(session=session, name="OtherProject", owner=user)
        exporter_project = await create_project(
            session=session, name="ExporterProject", owner=user
        )

        fleet = await create_fleet(
            session=session,
            project=exporter_project,
            name="fleet",
            spec=get_fleet_spec(get_ssh_fleet_configuration()),
        )
        await create_export(
            session=session,
            exporter_project=exporter_project,
            importer_projects=[other_project],
            exported_fleets=[fleet],
            name="test-export",
        )

        response = await client.post(
            f"/api/project/{project.name}/imports/list",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        assert response.json() == []
