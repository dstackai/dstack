from typing import Optional

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.models import ExportModel
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


class TestCreateExport:
    async def test_returns_403_if_not_authenticated(self, client: AsyncClient):
        response = await client.post(
            "/api/project/TestProject/exports/create",
            json={
                "name": "test-export",
                "importer_projects": ["OtherProject"],
                "exported_fleets": ["fleet1"],
            },
        )
        assert response.status_code in [401, 403]

    async def test_returns_403_if_not_admin(self, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = await client.post(
            f"/api/project/{project.name}/exports/create",
            headers=get_auth_headers(user.token),
            json={
                "name": "test-export",
                "importer_projects": ["OtherProject"],
                "exported_fleets": ["fleet1"],
            },
        )
        assert response.status_code == 403

    @pytest.mark.parametrize(
        ("global_role", "importer_project_role"),
        [(GlobalRole.ADMIN, None), (GlobalRole.USER, ProjectRole.ADMIN)],
    )
    async def test_creates_export(
        self,
        session: AsyncSession,
        client: AsyncClient,
        global_role: GlobalRole,
        importer_project_role: Optional[ProjectRole],
    ):
        user = await create_user(session=session, global_role=global_role)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )

        importer_project = await create_project(
            session=session, name="ImporterProject", owner=user
        )
        if importer_project_role is not None:
            await add_project_member(
                session=session,
                project=importer_project,
                user=user,
                project_role=importer_project_role,
            )
        await create_fleet(
            session=session,
            project=project,
            name="fleet1",
            spec=get_fleet_spec(get_ssh_fleet_configuration()),
        )

        response = await client.post(
            f"/api/project/{project.name}/exports/create",
            headers=get_auth_headers(user.token),
            json={
                "name": "test-export",
                "importer_projects": ["ImporterProject"],
                "exported_fleets": ["fleet1"],
            },
        )
        assert response.status_code == 200
        export_response = response.json()
        assert export_response["name"] == "test-export"
        assert len(export_response["imports"]) == 1
        assert export_response["imports"][0]["project_name"] == "ImporterProject"
        assert len(export_response["exported_fleets"]) == 1
        assert export_response["exported_fleets"][0]["name"] == "fleet1"

        res = await session.execute(select(ExportModel).where(ExportModel.name == "test-export"))
        assert res.scalar() is not None

    async def test_creates_empty_export(self, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )

        response = await client.post(
            f"/api/project/{project.name}/exports/create",
            headers=get_auth_headers(user.token),
            json={
                "name": "empty-export",
            },
        )
        assert response.status_code == 200
        export_response = response.json()
        assert export_response["name"] == "empty-export"
        assert len(export_response["imports"]) == 0
        assert len(export_response["exported_fleets"]) == 0

        res = await session.execute(select(ExportModel).where(ExportModel.name == "empty-export"))
        assert res.scalar() is not None

    @pytest.mark.parametrize(
        "body,error",
        [
            pytest.param(
                {
                    "name": "test-export",
                    "importer_projects": ["nonexistent"],
                },
                "Projects {'nonexistent'} not found or you are not allowed to add them as importers",
                id="nonexistent-project",
            ),
            pytest.param(
                {
                    "name": "test-export",
                    "importer_projects": ["NotPermittedProject"],
                },
                "Projects {'notpermittedproject'} not found or you are not allowed to add them as importers",
                id="not-permitted-project",
            ),
            pytest.param(
                {
                    "name": "test-export",
                    "exported_fleets": ["nonexistent-fleet"],
                },
                "Fleets {'nonexistent-fleet'} not found in project 'ExporterProject'",
                id="nonexistent-fleet",
            ),
            pytest.param(
                {
                    "name": "test-export",
                    "importer_projects": [
                        "ImporterProject",
                        "iMpOrTeRpRoJeCt",
                    ],  # case-insensitive
                },
                "Some importer projects are listed for addition more than once",
                id="duplicate-project",
            ),
            pytest.param(
                {
                    "name": "test-export",
                    "exported_fleets": ["exported-fleet", "exported-fleet"],
                },
                "Some fleets are listed for addition more than once",
                id="duplicate-fleet",
            ),
            pytest.param(
                {
                    "name": "test-export",
                    "exported_fleets": ["cloud-fleet"],
                },
                "Fleets ['cloud-fleet'] are cloud fleets. Can only export SSH fleets",
                id="cloud-fleet",
            ),
            pytest.param(
                {
                    "name": "test-export",
                    "importer_projects": ["eXpOrTeRpRoJeCt"],  # case-insensitive
                },
                "Project 'ExporterProject' cannot import from itself",
                id="self-import",
            ),
            pytest.param(
                {
                    "name": "",
                },
                "Resource name should match regex '^[a-z][a-z0-9-]{1,40}$'",
                id="empty-name",
            ),
            pytest.param(
                {
                    "name": "a" * 256,
                },
                "Resource name should match regex '^[a-z][a-z0-9-]{1,40}$'",
                id="long-name",
            ),
            pytest.param(
                {
                    "name": "!@#$",
                },
                "Resource name should match regex '^[a-z][a-z0-9-]{1,40}$'",
                id="invalid-name",
            ),
        ],
    )
    async def test_rejects_invalid_export(
        self, session: AsyncSession, client: AsyncClient, body: dict, error: str
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, name="ExporterProject", owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        importer_project = await create_project(
            session=session, name="ImporterProject", owner=user
        )
        await add_project_member(
            session=session, project=importer_project, user=user, project_role=ProjectRole.ADMIN
        )
        await create_fleet(
            session=session,
            project=project,
            name="exported-fleet",
            spec=get_fleet_spec(get_ssh_fleet_configuration()),
        )
        await create_fleet(session=session, project=project, name="cloud-fleet")
        not_permitted_project = await create_project(
            session=session, name="NotPermittedProject", owner=user
        )
        await add_project_member(
            session=session,
            project=not_permitted_project,
            user=user,
            project_role=ProjectRole.USER,
        )

        response = await client.post(
            f"/api/project/{project.name}/exports/create",
            headers=get_auth_headers(user.token),
            json=body,
        )
        assert response.status_code == 400
        assert error in response.json()["detail"][0]["msg"]
        res = await session.execute(select(func.count()).select_from(ExportModel))
        assert res.scalar_one() == 0

    async def test_rejects_export_on_name_conflict(
        self, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, name="Project")
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        await create_export(
            session=session,
            exporter_project=project,
            importer_projects=[],
            exported_fleets=[],
            name="test-export",
        )

        response = await client.post(
            f"/api/project/{project.name}/exports/create",
            headers=get_auth_headers(user.token),
            json={"name": "test-export"},
        )
        assert response.status_code == 400
        assert response.json()["detail"][0]["code"] == "resource_exists"
        assert (
            response.json()["detail"][0]["msg"]
            == "Export 'test-export' already exists in project 'Project'"
        )
        res = await session.execute(select(func.count()).select_from(ExportModel))
        assert res.scalar_one() == 1


class TestUpdateExport:
    async def test_returns_403_if_not_authenticated(self, client: AsyncClient):
        response = await client.post(
            "/api/project/TestProject/exports/update",
            json={
                "name": "test-export",
            },
        )
        assert response.status_code in [401, 403]

    async def test_returns_403_if_not_admin(self, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = await client.post(
            f"/api/project/{project.name}/exports/update",
            headers=get_auth_headers(user.token),
            json={
                "name": "test-export",
            },
        )
        assert response.status_code == 403

    @pytest.mark.parametrize(
        ("global_role", "importer_project_role"),
        [(GlobalRole.ADMIN, None), (GlobalRole.USER, ProjectRole.ADMIN)],
    )
    async def test_updates_export(
        self,
        session: AsyncSession,
        client: AsyncClient,
        global_role: GlobalRole,
        importer_project_role: Optional[ProjectRole],
    ):
        user = await create_user(session=session, global_role=global_role)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )

        other_project = await create_project(session=session, name="OtherProject", owner=user)
        another_project = await create_project(session=session, name="AnotherProject", owner=user)
        fleet1 = await create_fleet(
            session=session,
            project=project,
            name="fleet1",
            spec=get_fleet_spec(get_ssh_fleet_configuration()),
        )
        fleet2 = await create_fleet(
            session=session,
            project=project,
            name="fleet2",
            spec=get_fleet_spec(get_ssh_fleet_configuration()),
        )
        export = await create_export(
            session=session,
            exporter_project=project,
            importer_projects=[other_project, another_project],
            exported_fleets=[fleet1, fleet2],
            name="test-export",
        )

        new_project1 = await create_project(session=session, name="NewProject1", owner=user)
        new_project2 = await create_project(session=session, name="NewProject2", owner=user)
        await create_fleet(
            session=session,
            project=project,
            name="fleet3",
            spec=get_fleet_spec(get_ssh_fleet_configuration()),
        )
        await create_fleet(
            session=session,
            project=project,
            name="fleet4",
            spec=get_fleet_spec(get_ssh_fleet_configuration()),
        )
        if importer_project_role is not None:
            await add_project_member(
                session=session, project=new_project1, user=user, project_role=ProjectRole.ADMIN
            )
            await add_project_member(
                session=session, project=new_project2, user=user, project_role=ProjectRole.ADMIN
            )

        response = await client.post(
            f"/api/project/{project.name}/exports/update",
            headers=get_auth_headers(user.token),
            json={
                "name": "test-export",
                "add_importer_projects": ["NewProject1", "NewProject2"],
                "remove_importer_projects": ["AnotherProject"],
                "add_exported_fleets": ["fleet3", "fleet4"],
                "remove_exported_fleets": ["fleet2"],
            },
        )
        assert response.status_code == 200
        export_response = response.json()

        assert export_response["name"] == "test-export"
        assert len(export_response["imports"]) == 3
        assert {imp["project_name"] for imp in export_response["imports"]} == {
            "OtherProject",
            "NewProject1",
            "NewProject2",
        }
        assert len(export_response["exported_fleets"]) == 3
        assert {fleet["name"] for fleet in export_response["exported_fleets"]} == {
            "fleet1",
            "fleet3",
            "fleet4",
        }

        await session.refresh(export, ["imports", "exported_fleets"])
        assert len(export.imports) == 3
        assert len(export.exported_fleets) == 3

        response = await client.post(
            f"/api/project/{project.name}/exports/list", headers=get_auth_headers(user.token)
        )
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0] == export_response

    async def test_can_add_same_entities_as_existing_deleted_ones(
        self, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )

        deleted_importer_project = await create_project(
            session=session, name="_deleted_ImporterProject", owner=user, deleted=True
        )
        importer_project = await create_project(
            session=session, name="ImporterProject", owner=user
        )
        await add_project_member(
            session=session, project=importer_project, user=user, project_role=ProjectRole.ADMIN
        )
        deleted_fleet = await create_fleet(
            session=session,
            project=project,
            name="fleet",
            spec=get_fleet_spec(get_ssh_fleet_configuration()),
            deleted=True,
        )
        fleet = await create_fleet(
            session=session,
            project=project,
            name=deleted_fleet.name,
            spec=get_fleet_spec(get_ssh_fleet_configuration()),
        )
        export = await create_export(
            session=session,
            exporter_project=project,
            importer_projects=[deleted_importer_project],
            exported_fleets=[deleted_fleet],
            name="test-export",
        )

        response = await client.post(
            f"/api/project/{project.name}/exports/update",
            headers=get_auth_headers(user.token),
            json={
                "name": "test-export",
                "add_importer_projects": ["ImporterProject"],
                "add_exported_fleets": ["fleet"],
            },
        )
        assert response.status_code == 200
        export_response = response.json()

        assert export_response["name"] == "test-export"
        assert len(export_response["imports"]) == 1
        assert export_response["imports"][0]["project_name"] == "ImporterProject"
        assert len(export_response["exported_fleets"]) == 1
        assert export_response["exported_fleets"][0]["name"] == "fleet"
        assert export_response["exported_fleets"][0]["id"] == str(fleet.id)

        await session.refresh(export, ["imports", "exported_fleets"])
        # deleted imports and fleets are still in the database, just not returned in the response
        assert len(export.imports) == 2
        assert len(export.exported_fleets) == 2

        response = await client.post(
            f"/api/project/{project.name}/exports/list", headers=get_auth_headers(user.token)
        )
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0] == export_response

    @pytest.mark.parametrize(
        "body,error",
        [
            pytest.param(
                {
                    "name": "nonexistent-export",
                    "add_importer_projects": ["NotImporterProject"],
                },
                "Export 'nonexistent-export' not found in project 'ExporterProject'",
                id="nonexistent-export",
            ),
            pytest.param(
                {
                    "name": "test-export",
                },
                "No changes specified",
                id="no-changes",
            ),
            pytest.param(
                {
                    "name": "test-export",
                    "add_importer_projects": ["nonexistent"],
                },
                "Projects {'nonexistent'} not found or you are not allowed to add them as importers",
                id="add-nonexistent-project",
            ),
            pytest.param(
                {
                    "name": "test-export",
                    "add_importer_projects": ["NotPermittedProject"],
                },
                "Projects {'notpermittedproject'} not found or you are not allowed to add them as importers",
                id="add-not-permitted-project",
            ),
            pytest.param(
                {
                    "name": "test-export",
                    "add_exported_fleets": ["nonexistent-fleet"],
                },
                "Fleets {'nonexistent-fleet'} not found in project 'ExporterProject'",
                id="add-nonexistent-fleet",
            ),
            pytest.param(
                {
                    "name": "test-export",
                    "add_importer_projects": ["iMpOrTeRpRoJeCt"],  # case-insensitive
                },
                "Projects {'importerproject'} are already importing export 'test-export'",
                id="add-already-added-project",
            ),
            pytest.param(
                {
                    "name": "test-export",
                    "add_importer_projects": [
                        "ImporterProject",
                        "iMpOrTeRpRoJeCt",
                    ],  # case-insensitive
                },
                "Some importer projects are listed for addition more than once",
                id="add-duplicate-project",
            ),
            pytest.param(
                {
                    "name": "test-export",
                    "add_exported_fleets": ["exported-fleet"],
                },
                "Fleets {'exported-fleet'} are already exported by export 'test-export'",
                id="add-already-added-fleet",
            ),
            pytest.param(
                {
                    "name": "test-export",
                    "add_exported_fleets": ["exported-fleet", "exported-fleet"],
                },
                "Some fleets are listed for addition more than once",
                id="add-duplicate-fleet",
            ),
            pytest.param(
                {
                    "name": "test-export",
                    "add_exported_fleets": ["cloud-fleet"],
                },
                "Fleets ['cloud-fleet'] are cloud fleets. Can only export SSH fleets",
                id="add-cloud-fleet",
            ),
            pytest.param(
                {
                    "name": "test-export",
                    "add_importer_projects": ["eXpOrTeRpRoJeCt"],  # case-insensitive
                },
                "Project 'ExporterProject' cannot import from itself",
                id="add-self-import",
            ),
            pytest.param(
                {
                    "name": "test-export",
                    "remove_importer_projects": ["NotImporterProject"],
                },
                "Projects {'notimporterproject'} are not importing export 'test-export'",
                id="remove-not-added-project",
            ),
            pytest.param(
                {
                    "name": "test-export",
                    "remove_importer_projects": ["nonexistent"],
                },
                "Projects {'nonexistent'} are not importing export 'test-export'",
                id="remove-nonexistent-project",
            ),
            pytest.param(
                {
                    "name": "test-export",
                    "remove_exported_fleets": ["not-exported-fleet"],
                },
                "Fleets {'not-exported-fleet'} are not exported by export 'test-export'",
                id="remove-not-exported-fleet",
            ),
            pytest.param(
                {
                    "name": "test-export",
                    "remove_exported_fleets": ["nonexistent-fleet"],
                },
                "Fleets {'nonexistent-fleet'} are not exported by export 'test-export'",
                id="remove-nonexistent-fleet",
            ),
            pytest.param(
                {
                    "name": "test-export",
                    "remove_importer_projects": [
                        "ImporterProject",
                        "iMpOrTeRpRoJeCt",
                    ],  # case-insensitive
                },
                "Some importer projects are listed for removal more than once",
                id="remove-duplicate-project",
            ),
            pytest.param(
                {
                    "name": "test-export",
                    "remove_exported_fleets": ["exported-fleet", "exported-fleet"],
                },
                "Some fleets are listed for removal more than once",
                id="remove-duplicate-fleet",
            ),
            pytest.param(
                {
                    "name": "test-export",
                    "add_importer_projects": ["NotImporterProject"],
                    "remove_importer_projects": ["NoTiMpOrTeRpRoJeCt"],  # case-insensitive
                },
                "Projects {'notimporterproject'} are listed for both addition and removal. Cannot add and remove at the same time",
                id="add-remove-same-project",
            ),
            pytest.param(
                {
                    "name": "test-export",
                    "add_exported_fleets": ["not-exported-fleet"],
                    "remove_exported_fleets": ["not-exported-fleet"],
                },
                "Fleets {'not-exported-fleet'} are listed for both addition and removal. Cannot add and remove at the same time",
                id="add-remove-same-fleet",
            ),
        ],
    )
    async def test_rejects_invalid_update(
        self, session: AsyncSession, client: AsyncClient, body: dict, error: str
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, name="ExporterProject", owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        importer_project = await create_project(
            session=session, name="ImporterProject", owner=user
        )
        await add_project_member(
            session=session, project=importer_project, user=user, project_role=ProjectRole.ADMIN
        )
        exported_fleet = await create_fleet(
            session=session,
            project=project,
            name="exported-fleet",
            spec=get_fleet_spec(get_ssh_fleet_configuration()),
        )
        await create_export(
            session=session,
            exporter_project=project,
            importer_projects=[importer_project],
            exported_fleets=[exported_fleet],
            name="test-export",
        )
        await create_fleet(session=session, project=project, name="cloud-fleet")
        await create_fleet(
            session=session,
            project=project,
            name="not-exported-fleet",
            spec=get_fleet_spec(get_ssh_fleet_configuration()),
        )
        not_importer_project = await create_project(
            session=session, name="NotImporterProject", owner=user
        )
        await add_project_member(
            session=session,
            project=not_importer_project,
            user=user,
            project_role=ProjectRole.ADMIN,
        )
        not_permitted_project = await create_project(
            session=session, name="NotPermittedProject", owner=user
        )
        await add_project_member(
            session=session,
            project=not_permitted_project,
            user=user,
            project_role=ProjectRole.USER,
        )

        response = await client.post(
            f"/api/project/{project.name}/exports/list", headers=get_auth_headers(user.token)
        )
        assert response.status_code == 200
        canonical_exports = response.json()

        response = await client.post(
            f"/api/project/{project.name}/exports/update",
            headers=get_auth_headers(user.token),
            json=body,
        )
        assert response.status_code == 400
        assert error in response.json()["detail"][0]["msg"]

        response = await client.post(
            f"/api/project/{project.name}/exports/list",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        assert response.json() == canonical_exports


class TestDeleteExport:
    async def test_returns_403_if_not_authenticated(self, client: AsyncClient):
        response = await client.post(
            "/api/project/TestProject/exports/delete",
            json={"name": "test-export"},
        )
        assert response.status_code in [401, 403]

    async def test_returns_403_if_not_admin(self, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        response = await client.post(
            f"/api/project/{project.name}/exports/delete",
            headers=get_auth_headers(user.token),
            json={"name": "test-export"},
        )
        assert response.status_code == 403

    async def test_deletes_export(self, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )

        other_project = await create_project(session=session, name="OtherProject", owner=user)
        fleet = await create_fleet(
            session=session,
            project=project,
            name="fleet1",
            spec=get_fleet_spec(get_ssh_fleet_configuration()),
        )
        await create_export(
            session=session,
            exporter_project=project,
            importer_projects=[other_project],
            exported_fleets=[fleet],
            name="test-export",
        )

        response = await client.post(
            f"/api/project/{project.name}/exports/delete",
            headers=get_auth_headers(user.token),
            json={"name": "test-export"},
        )
        assert response.status_code == 200

        res = await session.execute(select(ExportModel).where(ExportModel.name == "test-export"))
        assert res.scalar() is None

    async def test_returns_400_for_nonexistent_export(
        self, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        response = await client.post(
            f"/api/project/{project.name}/exports/delete",
            headers=get_auth_headers(user.token),
            json={"name": "nonexistent-export"},
        )
        assert response.status_code == 400
        assert response.json()["detail"][0]["code"] == "resource_not_exists"


class TestListExports:
    async def test_returns_403_if_not_authenticated(self, client: AsyncClient):
        response = await client.post(
            "/api/project/TestProject/exports/list",
        )
        assert response.status_code in [401, 403]

    async def test_returns_403_if_not_member(self, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        response = await client.post(
            f"/api/project/{project.name}/exports/list",
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
    async def test_lists_exports(
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

        other_project = await create_project(session=session, name="OtherProject", owner=user)
        fleet1 = await create_fleet(
            session=session,
            project=project,
            name="fleet1",
            spec=get_fleet_spec(get_ssh_fleet_configuration()),
        )
        fleet2 = await create_fleet(
            session=session,
            project=project,
            name="fleet2",
            spec=get_fleet_spec(get_ssh_fleet_configuration()),
        )
        for name, fleet in (("export1", fleet1), ("export2", fleet2)):
            await create_export(
                session=session,
                exporter_project=project,
                importer_projects=[other_project],
                exported_fleets=[fleet],
                name=name,
            )

        response = await client.post(
            f"/api/project/{project.name}/exports/list",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        exports = response.json()
        assert len(exports) == 2
        exports.sort(key=lambda e: e["name"])

        assert exports[0]["name"] == "export1"
        assert len(exports[0]["imports"]) == 1
        assert exports[0]["imports"][0]["project_name"] == "OtherProject"
        assert len(exports[0]["exported_fleets"]) == 1
        assert exports[0]["exported_fleets"][0]["name"] == "fleet1"

        assert exports[1]["name"] == "export2"
        assert len(exports[1]["imports"]) == 1
        assert exports[1]["imports"][0]["project_name"] == "OtherProject"
        assert len(exports[1]["exported_fleets"]) == 1
        assert exports[1]["exported_fleets"][0]["name"] == "fleet2"

    @pytest.mark.parametrize(
        "global_role, project_role",
        [
            (GlobalRole.ADMIN, None),
            (GlobalRole.USER, ProjectRole.USER),
        ],
    )
    async def test_returns_empty_list_when_no_exports(
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
            f"/api/project/{project.name}/exports/list",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        assert response.json() == []

    async def test_not_includes_deleted_entities(self, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )

        importer_project = await create_project(
            session=session, name="ImporterProject", owner=user
        )
        deleted_importer_project = await create_project(
            session=session, name="DeletedImporterProject", owner=user, deleted=True
        )
        fleet = await create_fleet(
            session=session,
            project=project,
            name="fleet",
            spec=get_fleet_spec(get_ssh_fleet_configuration()),
        )
        deleted_fleet = await create_fleet(
            session=session,
            project=project,
            name="deleted-fleet",
            spec=get_fleet_spec(get_ssh_fleet_configuration()),
            deleted=True,
        )
        await create_export(
            session=session,
            exporter_project=project,
            importer_projects=[importer_project, deleted_importer_project],
            exported_fleets=[fleet, deleted_fleet],
            name="test-export",
        )

        response = await client.post(
            f"/api/project/{project.name}/exports/list",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200
        exports = response.json()
        assert len(exports) == 1
        assert exports[0]["name"] == "test-export"
        assert len(exports[0]["imports"]) == 1
        assert exports[0]["imports"][0]["project_name"] == "ImporterProject"
        assert len(exports[0]["exported_fleets"]) == 1
        assert exports[0]["exported_fleets"][0]["name"] == "fleet"
