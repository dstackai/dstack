from typing import Optional

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.testing.common import (
    create_export,
    create_fleet,
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
        await create_export(
            session=session,
            exporter_project=exporter_project1,
            importer_projects=[importer_project],
            exported_fleets=[fleet1],
            name="export1",
        )
        await create_export(
            session=session,
            exporter_project=exporter_project2,
            importer_projects=[importer_project],
            exported_fleets=[fleet2],
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

        assert imports[1]["export"]["name"] == "export2"
        assert imports[1]["export"]["project_name"] == "ExporterProject2"
        assert len(imports[1]["export"]["exported_fleets"]) == 1
        assert imports[1]["export"]["exported_fleets"][0]["name"] == "fleet2"

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
