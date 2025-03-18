from datetime import datetime, timezone
from unittest.mock import patch
from uuid import UUID

import pytest
from freezegun import freeze_time
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.models import MemberModel, ProjectModel
from dstack._internal.server.services.permissions import DefaultPermissions
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.testing.common import (
    create_backend,
    create_project,
    create_user,
    default_permissions_context,
    get_auth_headers,
)


class TestListProjects:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_40x_if_not_authenticated(self, test_db, client: AsyncClient):
        response = await client.post("/api/projects/list")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_empty_list(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session)
        response = await client.post("/api/projects/list", headers=get_auth_headers(user.token))
        assert response.status_code in [200]
        assert response.json() == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_projects(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(
            session=session,
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        project = await create_project(
            session=session,
            owner=user,
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        await create_backend(
            session=session,
            project_id=project.id,
        )
        response = await client.post("/api/projects/list", headers=get_auth_headers(user.token))
        assert response.status_code in [200]
        assert response.json() == [
            {
                "project_id": str(project.id),
                "project_name": project.name,
                "owner": {
                    "id": str(user.id),
                    "username": user.name,
                    "created_at": "2023-01-02T03:04:00+00:00",
                    "global_role": user.global_role,
                    "email": None,
                    "active": True,
                    "permissions": {
                        "can_create_projects": True,
                    },
                },
                "created_at": "2023-01-02T03:04:00+00:00",
                "backends": [],
                "members": [],
            }
        ]


class TestCreateProject:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_40x_if_not_authenticated(self, test_db, client: AsyncClient):
        response = await client.post("/api/projects/create")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @freeze_time(datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc))
    async def test_creates_project(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session)
        project_id = UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e")
        project_name = "test_project"
        body = {"project_name": project_name}
        with patch("uuid.uuid4") as m:
            m.return_value = project_id
            response = await client.post(
                "/api/projects/create",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 200, response.json()
        assert response.json() == {
            "project_id": str(project_id),
            "project_name": project_name,
            "owner": {
                "id": str(user.id),
                "username": user.name,
                "created_at": "2023-01-02T03:04:00+00:00",
                "global_role": user.global_role,
                "email": None,
                "active": True,
                "permissions": {
                    "can_create_projects": True,
                },
            },
            "created_at": "2023-01-02T03:04:00+00:00",
            "backends": [],
            "members": [
                {
                    "user": {
                        "id": str(user.id),
                        "username": user.name,
                        "created_at": "2023-01-02T03:04:00+00:00",
                        "global_role": user.global_role,
                        "email": None,
                        "active": True,
                        "permissions": {
                            "can_create_projects": True,
                        },
                    },
                    "project_role": ProjectRole.ADMIN,
                    "permissions": {
                        "can_manage_ssh_fleets": True,
                    },
                }
            ],
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_400_if_project_name_is_taken(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session)
        with patch("uuid.uuid4") as m:
            m.return_value = UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e")
            response = await client.post(
                "/api/projects/create",
                headers=get_auth_headers(user.token),
                json={"project_name": "TestProject"},
            )
        assert response.status_code == 200
        # Project name uniqueness check should be case insensitive
        for project_name in ["testproject", "TestProject", "TESTPROJECT"]:
            with patch("uuid.uuid4") as m:
                m.return_value = UUID("2b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e")
                response = await client.post(
                    "/api/projects/create",
                    headers=get_auth_headers(user.token),
                    json={"project_name": project_name},
                )
            assert response.status_code == 400
        res = await session.execute(
            select(ProjectModel).where(
                ProjectModel.name.in_(["TestProject", "testproject", "TestProject", "TESTPROJECT"])
            )
        )
        assert len(res.scalars().all()) == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_400_if_user_project_quota_exceeded(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, name="owner", global_role=GlobalRole.USER)
        for i in range(10):
            response = await client.post(
                "/api/projects/create",
                headers=get_auth_headers(user.token),
                json={"project_name": f"project{i}"},
            )
            assert response.status_code == 200, response.json()
        response = await client.post(
            "/api/projects/create",
            headers=get_auth_headers(user.token),
            json={"project_name": "project11"},
        )
        assert response.status_code == 400
        assert response.json() == {
            "detail": [{"code": "error", "msg": "User project quota exceeded"}]
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_no_project_quota_for_global_admins(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, name="owner", global_role=GlobalRole.ADMIN)
        for i in range(12):
            response = await client.post(
                "/api/projects/create",
                headers=get_auth_headers(user.token),
                json={"project_name": f"project{i}"},
            )
            assert response.status_code == 200, response.json()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_forbids_if_no_permission_to_create_projects(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        with default_permissions_context(
            DefaultPermissions(allow_non_admins_create_projects=False)
        ):
            response = await client.post(
                "/api/projects/create",
                headers=get_auth_headers(user.token),
                json={"project_name": "new_project"},
            )
        assert response.status_code in [401, 403]


class TestDeleteProject:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_40x_if_not_authenticated(self, test_db, client: AsyncClient):
        response = await client.post("/api/projects/delete")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_cannot_delete_the_only_project(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        response = await client.post(
            "/api/projects/delete",
            headers=get_auth_headers(user.token),
            json={"projects_names": [project.name]},
        )
        assert response.status_code == 400
        await session.refresh(project)
        assert not project.deleted

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_deletes_projects(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project1 = await create_project(session=session, owner=user, name="project1")
        await add_project_member(
            session=session, project=project1, user=user, project_role=ProjectRole.ADMIN
        )
        project2 = await create_project(session=session, owner=user, name="project2")
        await add_project_member(
            session=session, project=project2, user=user, project_role=ProjectRole.ADMIN
        )
        response = await client.post(
            "/api/projects/delete",
            headers=get_auth_headers(user.token),
            json={"projects_names": [project1.name]},
        )
        assert response.status_code == 200
        await session.refresh(project1)
        await session.refresh(project2)
        assert project1.deleted
        assert not project2.deleted

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_403_if_not_project_admin(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        owner = await create_user(session=session, name="owner", global_role=GlobalRole.USER)
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project1 = await create_project(session=session, name="project1", owner=owner)
        project2 = await create_project(session=session, name="project2", owner=owner)
        await add_project_member(
            session=session, project=project1, user=user, project_role=ProjectRole.ADMIN
        )
        await add_project_member(
            session=session, project=project2, user=user, project_role=ProjectRole.USER
        )
        response = await client.post(
            "/api/projects/delete",
            headers=get_auth_headers(user.token),
            json={"projects_names": [project1.name, project2.name]},
        )
        assert response.status_code == 403
        res = await session.execute(select(ProjectModel))
        assert len(res.all()) == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_403_if_not_project_member(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, name="project")
        response = await client.post(
            "/api/projects/delete",
            headers=get_auth_headers(user.token),
            json={"projects_names": [project.name]},
        )
        assert response.status_code == 403
        res = await session.execute(select(ProjectModel))
        assert len(res.all()) == 1


class TestGetProject:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_40x_if_not_authenticated(self, test_db, client: AsyncClient):
        response = await client.post("/api/projects/test_project/get")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_404_if_project_does_not_exist(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session)
        response = await client.post(
            "/api/projects/test_project/get",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 404, response.json()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_project(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(
            session=session,
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        project = await create_project(
            session=session,
            owner=user,
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        response = await client.post(
            "/api/projects/test_project/get",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 200, response.json()
        assert response.json() == {
            "project_id": str(project.id),
            "project_name": project.name,
            "owner": {
                "id": str(user.id),
                "username": user.name,
                "created_at": "2023-01-02T03:04:00+00:00",
                "global_role": user.global_role,
                "email": None,
                "active": True,
                "permissions": {
                    "can_create_projects": True,
                },
            },
            "created_at": "2023-01-02T03:04:00+00:00",
            "backends": [],
            "members": [
                {
                    "user": {
                        "id": str(user.id),
                        "username": user.name,
                        "created_at": "2023-01-02T03:04:00+00:00",
                        "global_role": user.global_role,
                        "email": None,
                        "active": True,
                        "permissions": {
                            "can_create_projects": True,
                        },
                    },
                    "project_role": ProjectRole.ADMIN,
                    "permissions": {
                        "can_manage_ssh_fleets": True,
                    },
                }
            ],
        }


class TestSetProjectMembers:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_40x_if_not_authenticated(self, test_db, client: AsyncClient):
        response = await client.post("/api/projects/test_project/get")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_sets_project_members(self, test_db, session: AsyncSession, client: AsyncClient):
        project = await create_project(
            session=session,
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        admin = await create_user(
            session=session,
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        await add_project_member(
            session=session,
            project=project,
            user=admin,
            project_role=ProjectRole.ADMIN,
        )
        user1 = await create_user(
            session=session,
            name="user1",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        user2 = await create_user(
            session=session,
            name="user2",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        members = [
            {
                "username": admin.name,
                "project_role": ProjectRole.ADMIN,
            },
            {
                "username": user1.name,
                "project_role": ProjectRole.ADMIN,
            },
            {
                "username": user2.name,
                "project_role": ProjectRole.USER,
            },
        ]
        body = {"members": members}
        response = await client.post(
            f"/api/projects/{project.name}/set_members",
            headers=get_auth_headers(admin.token),
            json=body,
        )
        assert response.status_code == 200, response.json()
        assert response.json()["members"] == [
            {
                "user": {
                    "id": str(admin.id),
                    "username": admin.name,
                    "created_at": "2023-01-02T03:04:00+00:00",
                    "global_role": admin.global_role,
                    "email": None,
                    "active": True,
                    "permissions": {
                        "can_create_projects": True,
                    },
                },
                "project_role": ProjectRole.ADMIN,
                "permissions": {
                    "can_manage_ssh_fleets": True,
                },
            },
            {
                "user": {
                    "id": str(user1.id),
                    "username": user1.name,
                    "created_at": "2023-01-02T03:04:00+00:00",
                    "global_role": user1.global_role,
                    "email": None,
                    "active": True,
                    "permissions": {
                        "can_create_projects": True,
                    },
                },
                "project_role": ProjectRole.ADMIN,
                "permissions": {
                    "can_manage_ssh_fleets": True,
                },
            },
            {
                "user": {
                    "id": str(user2.id),
                    "username": user2.name,
                    "created_at": "2023-01-02T03:04:00+00:00",
                    "global_role": user2.global_role,
                    "email": None,
                    "active": True,
                    "permissions": {
                        "can_create_projects": True,
                    },
                },
                "project_role": ProjectRole.USER,
                "permissions": {
                    "can_manage_ssh_fleets": True,
                },
            },
        ]
        res = await session.execute(select(MemberModel))
        members = res.scalars().all()
        assert len(members) == 3

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_sets_project_members_by_email(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        project = await create_project(
            session=session,
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        admin = await create_user(
            session=session,
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
            global_role=GlobalRole.ADMIN,
        )
        user1 = await create_user(
            session=session,
            name="user1",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
            email="testemail@example.com",
        )
        members = [
            {
                "username": user1.email,
                "project_role": ProjectRole.ADMIN,
            },
        ]
        body = {"members": members}
        response = await client.post(
            f"/api/projects/{project.name}/set_members",
            headers=get_auth_headers(admin.token),
            json=body,
        )
        assert response.status_code == 200, response.json()
        assert response.json()["members"] == [
            {
                "user": {
                    "id": str(user1.id),
                    "username": user1.name,
                    "created_at": "2023-01-02T03:04:00+00:00",
                    "global_role": user1.global_role,
                    "email": user1.email,
                    "active": True,
                    "permissions": {
                        "can_create_projects": True,
                    },
                },
                "project_role": ProjectRole.ADMIN,
                "permissions": {
                    "can_manage_ssh_fleets": True,
                },
            },
        ]
        res = await session.execute(select(MemberModel))
        members = res.scalars().all()
        assert len(members) == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_manager_cannot_set_project_admins(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        project = await create_project(session=session)
        user = await create_user(session=session, global_role=GlobalRole.USER)
        await add_project_member(
            session=session,
            project=project,
            user=user,
            project_role=ProjectRole.MANAGER,
        )
        user1 = await create_user(session=session, name="user1")
        members = [
            {
                "username": user.name,
                "project_role": ProjectRole.ADMIN,
            },
            {
                "username": user1.name,
                "project_role": ProjectRole.ADMIN,
            },
        ]
        body = {"members": members}
        response = await client.post(
            f"/api/projects/{project.name}/set_members",
            headers=get_auth_headers(user.token),
            json=body,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_global_admin_manager_can_set_project_admins(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        project = await create_project(session=session)
        user = await create_user(session=session, global_role=GlobalRole.ADMIN)
        await add_project_member(
            session=session,
            project=project,
            user=user,
            project_role=ProjectRole.MANAGER,
        )
        user1 = await create_user(session=session, name="user1")
        members = [
            {
                "username": user.name,
                "project_role": ProjectRole.ADMIN,
            },
            {
                "username": user1.name,
                "project_role": ProjectRole.ADMIN,
            },
        ]
        body = {"members": members}
        response = await client.post(
            f"/api/projects/{project.name}/set_members",
            headers=get_auth_headers(user.token),
            json=body,
        )
        assert response.status_code == 200
        res = await session.execute(select(MemberModel))
        members = res.scalars().all()
        assert len(members) == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_non_manager_cannot_set_project_members(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        project = await create_project(session=session)
        user = await create_user(session=session, global_role=GlobalRole.USER)
        await add_project_member(
            session=session,
            project=project,
            user=user,
            project_role=ProjectRole.USER,
        )
        user1 = await create_user(session=session, name="user1")
        members = [
            {
                "username": user.name,
                "project_role": ProjectRole.ADMIN,
            },
            {
                "username": user1.name,
                "project_role": ProjectRole.ADMIN,
            },
        ]
        body = {"members": members}
        response = await client.post(
            f"/api/projects/{project.name}/set_members",
            headers=get_auth_headers(user.token),
            json=body,
        )
        assert response.status_code == 403
