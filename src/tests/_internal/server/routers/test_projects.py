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
                "is_public": False,
            }
        ]

<<<<<<< HEAD
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_public_projects_to_non_members(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Create project owner
        owner = await create_user(
            session=session,
            name="owner",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
            global_role=GlobalRole.USER,
        )

        # Create a different user who is not a member
        non_member = await create_user(
            session=session,
            name="non_member",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
            global_role=GlobalRole.USER,
        )

        # Create a public project
        public_project = await create_project(
            session=session,
            owner=owner,
            name="public_project",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
            is_public=True,
        )

        # Create a private project
        private_project = await create_project(
            session=session,
            owner=owner,
            name="private_project",
            created_at=datetime(2023, 1, 2, 3, 5, tzinfo=timezone.utc),
            is_public=False,
        )

        # Add owner as admin to both projects
        await add_project_member(
            session=session, project=public_project, user=owner, project_role=ProjectRole.ADMIN
        )
        await add_project_member(
            session=session, project=private_project, user=owner, project_role=ProjectRole.ADMIN
        )

        # List projects as non-member - should only see public project
        response = await client.post(
            "/api/projects/list", headers=get_auth_headers(non_member.token)
        )
        assert response.status_code == 200
        projects = response.json()

        # Should only see the public project
        assert len(projects) == 1
        assert projects[0]["project_name"] == "public_project"
        assert projects[0]["is_public"] is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_member_sees_both_public_and_private_projects(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Create project owner
        owner = await create_user(
            session=session,
            name="owner",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
            global_role=GlobalRole.USER,
        )

        # Create a user who will be a member
        member = await create_user(
            session=session,
            name="member",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
            global_role=GlobalRole.USER,
        )

        # Create a public project
        public_project = await create_project(
            session=session,
            owner=owner,
            name="public_project",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
            is_public=True,
        )

        # Create a private project
        private_project = await create_project(
            session=session,
            owner=owner,
            name="private_project",
            created_at=datetime(2023, 1, 2, 3, 5, tzinfo=timezone.utc),
            is_public=False,
        )

        # Add member to the private project only
        await add_project_member(
            session=session, project=private_project, user=member, project_role=ProjectRole.USER
        )

        # Add owner as admin to both projects
        await add_project_member(
            session=session, project=public_project, user=owner, project_role=ProjectRole.ADMIN
        )
        await add_project_member(
            session=session, project=private_project, user=owner, project_role=ProjectRole.ADMIN
        )

        # List projects as member - should see both projects
        response = await client.post("/api/projects/list", headers=get_auth_headers(member.token))
        assert response.status_code == 200
        projects = response.json()

        # Should see both projects, sorted by created_at
        assert len(projects) == 2
        project_names = [p["project_name"] for p in projects]
        assert "public_project" in project_names
        assert "private_project" in project_names

=======
>>>>>>> 7fc1b408 (fix: retrack PR2 based on PR1)

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
            "is_public": False,
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
<<<<<<< HEAD
            assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @freeze_time(datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc))
    async def test_creates_public_project(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session)
        project_id = UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e")
        project_name = "test_public_project"
        body = {"project_name": project_name, "is_public": True}
        with patch("uuid.uuid4") as m:
            m.return_value = project_id
            response = await client.post(
                "/api/projects/create",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 200, response.json()

        # Check that the response includes is_public=True
        response_data = response.json()
        assert "is_public" in response_data
        assert response_data["is_public"] is True

        # Verify the project was created as public in the database
        res = await session.execute(select(ProjectModel).where(ProjectModel.name == project_name))
        project = res.scalar_one()
        assert project.is_public is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @freeze_time(datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc))
    async def test_creates_private_project_by_default(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session)
        project_id = UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e")
        project_name = "test_private_project"
        body = {"project_name": project_name}

        with patch("uuid.uuid4", return_value=project_id):
            response = await client.post(
                "/api/projects/create",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 200, response.json()

        # Check that the response includes is_public=False (default)
        response_data = response.json()
        assert "is_public" in response_data
        assert response_data["is_public"] is False

        # Verify the project was created as private in the database
        res = await session.execute(select(ProjectModel).where(ProjectModel.name == project_name))
        project = res.scalar_one()
        assert project.is_public is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @freeze_time(datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc))
    async def test_creates_private_project_explicitly(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session)
        project_id = UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e")
        project_name = "test_explicit_private_project"
        body = {"project_name": project_name, "is_public": False}

        with patch("uuid.uuid4", return_value=project_id):
            response = await client.post(
                "/api/projects/create",
                headers=get_auth_headers(user.token),
                json=body,
            )
        assert response.status_code == 200, response.json()

        # Check that the response includes is_public=False (explicit)
        response_data = response.json()
        assert "is_public" in response_data
        assert response_data["is_public"] is False

        # Verify the project was created as private in the database
        res = await session.execute(select(ProjectModel).where(ProjectModel.name == project_name))
        project = res.scalar_one()
        assert project.is_public is False
=======
        assert response.status_code in [401, 403]
>>>>>>> 7fc1b408 (fix: retrack PR2 based on PR1)


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
            "is_public": False,
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_non_member_can_access_public_project(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Create project owner
        owner = await create_user(
            session=session,
            name="owner",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
            global_role=GlobalRole.USER,  # Make owner a regular user
        )

        # Create public project
        project = await create_project(
            session=session,
            owner=owner,
            name="public_project",
            is_public=True,
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        await add_project_member(
            session=session, project=project, user=owner, project_role=ProjectRole.ADMIN
        )

        # Create non-member user as regular user (not global admin)
        non_member = await create_user(
            session=session,
            name="non_member",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
            global_role=GlobalRole.USER,  # Make non_member a regular user
        )

        # Non-member should be able to access public project details
        response = await client.post(
            f"/api/projects/{project.name}/get",
            headers=get_auth_headers(non_member.token),
        )
        assert response.status_code == 200, response.json()

        # Verify response includes is_public=True
        response_data = response.json()
        assert response_data["is_public"] is True
        assert response_data["project_name"] == "public_project"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_non_member_cannot_access_private_project(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Create project owner
        owner = await create_user(
            session=session,
            name="owner",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
            global_role=GlobalRole.USER,  # Make owner a regular user
        )

        # Create private project
        project = await create_project(
            session=session,
            owner=owner,
            name="private_project",
            is_public=False,
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        await add_project_member(
            session=session, project=project, user=owner, project_role=ProjectRole.ADMIN
        )

        # Create non-member user as regular user (not global admin)
        non_member = await create_user(
            session=session,
            name="non_member",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
            global_role=GlobalRole.USER,  # Make non_member a regular user
        )

        # Non-member should NOT be able to access private project details
        response = await client.post(
            f"/api/projects/{project.name}/get",
            headers=get_auth_headers(non_member.token),
        )
        assert response.status_code == 403, response.json()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_member_can_access_both_public_and_private_projects(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Create project owner
        owner = await create_user(
            session=session,
            name="owner",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
            global_role=GlobalRole.USER,  # Make owner a regular user
        )

        # Create public project
        public_project = await create_project(
            session=session,
            owner=owner,
            name="public_project",
            is_public=True,
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        await add_project_member(
            session=session, project=public_project, user=owner, project_role=ProjectRole.ADMIN
        )

        # Create private project
        private_project = await create_project(
            session=session,
            owner=owner,
            name="private_project",
            is_public=False,
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        await add_project_member(
            session=session, project=private_project, user=owner, project_role=ProjectRole.ADMIN
        )

        # Create member user as regular user (not global admin) and add to both projects
        member = await create_user(
            session=session,
            name="member",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
            global_role=GlobalRole.USER,  # Make member a regular user
        )
        await add_project_member(
            session=session, project=public_project, user=member, project_role=ProjectRole.USER
        )
        await add_project_member(
            session=session, project=private_project, user=member, project_role=ProjectRole.USER
        )

        # Member should be able to access both public and private projects
        response = await client.post(
            f"/api/projects/{public_project.name}/get",
            headers=get_auth_headers(member.token),
        )
        assert response.status_code == 200, response.json()
        assert response.json()["is_public"] is True

        response = await client.post(
            f"/api/projects/{private_project.name}/get",
            headers=get_auth_headers(member.token),
        )
        assert response.status_code == 200, response.json()
        assert response.json()["is_public"] is False


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
    async def test_add_member_errors_on_nonexistent_user(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Setup project and admin
        project = await create_project(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        admin = await create_user(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        await add_project_member(
            session=session, project=project, user=admin, project_role=ProjectRole.ADMIN
        )

        # Try to add non-existent user - should now error instead of silently skipping
        body = {"members": [{"username": "nonexistent", "project_role": "user"}]}
        response = await client.post(
            f"/api/projects/{project.name}/add_members",
            headers=get_auth_headers(admin.token),
            json=body,
        )

        # Operation should fail with 400 error for non-existent user
        assert response.status_code == 400
        response_json = response.json()
        assert "User not found: nonexistent" in str(response_json)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_add_member_manager_cannot_add_admin_without_global_admin(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Setup project with manager (not global admin)
        project = await create_project(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        manager = await create_user(
            session=session,
            global_role=GlobalRole.USER,
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        await add_project_member(
            session=session, project=project, user=manager, project_role=ProjectRole.MANAGER
        )

        # Create user to add
        _new_user = await create_user(
            session=session,
            name="newuser",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )

        # Try to add admin
        body = {"members": [{"username": "newuser", "project_role": "admin"}]}
        response = await client.post(
            f"/api/projects/{project.name}/add_members",
            headers=get_auth_headers(manager.token),
            json=body,
        )

        assert response.status_code == 403


<<<<<<< HEAD
class TestListUserProjectsService:
    """Test the service-level functions for backward compatibility"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_list_user_projects_only_returns_member_projects(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Create project owner
        owner = await create_user(
            session=session,
            name="owner",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
            global_role=GlobalRole.USER,
        )

        # Create a different user who is not a member
        non_member = await create_user(
            session=session,
            name="non_member",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
            global_role=GlobalRole.USER,
        )

        # Create a public project
        public_project = await create_project(
            session=session,
            owner=owner,
            name="public_project",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
            is_public=True,
        )

        # Add owner as admin
        await add_project_member(
            session=session, project=public_project, user=owner, project_role=ProjectRole.ADMIN
        )

        # Test: list_user_projects should NOT return public projects for non-members
        from dstack._internal.server.services.projects import list_user_projects

        projects = await list_user_projects(session=session, user=non_member)
        assert len(projects) == 0  # Non-member should see NO projects

        # Test: list_user_projects should return projects where user IS a member
        projects = await list_user_projects(session=session, user=owner)
        assert len(projects) == 1
        assert projects[0].project_name == "public_project"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_list_user_accessible_projects_returns_member_and_public_projects(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Create project owner
        owner = await create_user(
            session=session,
            name="owner",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
            global_role=GlobalRole.USER,
        )

        # Create a different user who is not a member
        non_member = await create_user(
            session=session,
            name="non_member",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
            global_role=GlobalRole.USER,
        )

        # Create a public project
        public_project = await create_project(
            session=session,
            owner=owner,
            name="public_project",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
            is_public=True,
        )

        # Create a private project
        private_project = await create_project(
            session=session,
            owner=owner,
            name="private_project",
            created_at=datetime(2023, 1, 2, 3, 5, tzinfo=timezone.utc),
            is_public=False,
        )

        # Add owner as admin to both projects
        await add_project_member(
            session=session, project=public_project, user=owner, project_role=ProjectRole.ADMIN
        )
        await add_project_member(
            session=session, project=private_project, user=owner, project_role=ProjectRole.ADMIN
        )

        # Test: list_user_accessible_projects should return public projects for non-members
        from dstack._internal.server.services.projects import list_user_accessible_projects

        projects = await list_user_accessible_projects(session=session, user=non_member)
        assert len(projects) == 1  # Should see only the public project
        assert projects[0].project_name == "public_project"

        # Test: list_user_accessible_projects should return ALL projects for members
        projects = await list_user_accessible_projects(session=session, user=owner)
        assert len(projects) == 2  # Should see both projects
        project_names = [p.project_name for p in projects]
        assert "public_project" in project_names
        assert "private_project" in project_names
=======
class TestMemberManagement:
    """Test class for add_member and remove_member endpoints"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @pytest.mark.parametrize("endpoint", ["add_members", "remove_members"])
    async def test_returns_40x_if_not_authenticated(
        self, test_db, client: AsyncClient, endpoint: str
    ):
        response = await client.post(f"/api/projects/test-project/{endpoint}")
        assert response.status_code in [401, 403]

    # Add Member Tests
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_add_member_by_username(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Setup project and admin
        project = await create_project(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        admin = await create_user(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        await add_project_member(
            session=session, project=project, user=admin, project_role=ProjectRole.ADMIN
        )

        # Create user to add
        _new_user = await create_user(
            session=session,
            name="newuser",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )

        # Add member
        body = {"members": [{"username": "newuser", "project_role": "user"}]}
        response = await client.post(
            f"/api/projects/{project.name}/add_members",
            headers=get_auth_headers(admin.token),
            json=body,
        )

        assert response.status_code == 200
        response_data = response.json()

        # Check that new user is in the members list
        member_usernames = [member["user"]["username"] for member in response_data["members"]]
        assert "newuser" in member_usernames

        # Find the new member and check their role
        new_member = next(
            m for m in response_data["members"] if m["user"]["username"] == "newuser"
        )
        assert new_member["project_role"] == "user"

        # Verify in database
        res = await session.execute(select(MemberModel).where(MemberModel.user_id == _new_user.id))
        member = res.scalar_one()
        assert member.project_role == ProjectRole.USER

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_add_member_by_email(self, test_db, session: AsyncSession, client: AsyncClient):
        # Setup project and admin
        project = await create_project(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        admin = await create_user(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        await add_project_member(
            session=session, project=project, user=admin, project_role=ProjectRole.ADMIN
        )

        # Create user to add
        _new_user = await create_user(
            session=session,
            name="emailuser",
            email="test@example.com",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )

        # Add member by email
        body = {"members": [{"username": "test@example.com", "project_role": "manager"}]}
        response = await client.post(
            f"/api/projects/{project.name}/add_members",
            headers=get_auth_headers(admin.token),
            json=body,
        )

        assert response.status_code == 200
        response_data = response.json()

        # Check that new user is in the members list
        member_usernames = [member["user"]["username"] for member in response_data["members"]]
        assert "emailuser" in member_usernames

        # Find the new member and check their role
        new_member = next(
            m for m in response_data["members"] if m["user"]["username"] == "emailuser"
        )
        assert new_member["project_role"] == "manager"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_add_member_updates_existing_role(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Setup project and admin
        project = await create_project(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        admin = await create_user(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        await add_project_member(
            session=session, project=project, user=admin, project_role=ProjectRole.ADMIN
        )

        # Create user and add as USER first
        existing_user = await create_user(
            session=session,
            name="existing",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        await add_project_member(
            session=session, project=project, user=existing_user, project_role=ProjectRole.USER
        )

        # Update to MANAGER
        body = {"members": [{"username": "existing", "project_role": "manager"}]}
        response = await client.post(
            f"/api/projects/{project.name}/add_members",
            headers=get_auth_headers(admin.token),
            json=body,
        )

        assert response.status_code == 200
        response_data = response.json()

        # Find the updated member and check their role
        updated_member = next(
            m for m in response_data["members"] if m["user"]["username"] == "existing"
        )
        assert updated_member["project_role"] == "manager"

        # Verify in database
        res = await session.execute(
            select(MemberModel).where(MemberModel.user_id == existing_user.id)
        )
        member = res.scalar_one()
        assert member.project_role == ProjectRole.MANAGER

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_add_member_errors_on_nonexistent_user(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Setup project and admin
        project = await create_project(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        admin = await create_user(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        await add_project_member(
            session=session, project=project, user=admin, project_role=ProjectRole.ADMIN
        )

        # Try to add non-existent user - should now error instead of silently skipping
        body = {"members": [{"username": "nonexistent", "project_role": "user"}]}
        response = await client.post(
            f"/api/projects/{project.name}/add_members",
            headers=get_auth_headers(admin.token),
            json=body,
        )

        # Operation should fail with 400 error for non-existent user
        assert response.status_code == 400
        response_json = response.json()
        assert "User not found: nonexistent" in str(response_json)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_add_member_manager_cannot_add_admin_without_global_admin(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Setup project with manager (not global admin)
        project = await create_project(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        manager = await create_user(
            session=session,
            global_role=GlobalRole.USER,
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        await add_project_member(
            session=session, project=project, user=manager, project_role=ProjectRole.MANAGER
        )

        # Create user to add
        _new_user = await create_user(
            session=session,
            name="newuser",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )

        # Try to add admin
        body = {"members": [{"username": "newuser", "project_role": "admin"}]}
        response = await client.post(
            f"/api/projects/{project.name}/add_members",
            headers=get_auth_headers(manager.token),
            json=body,
        )

        assert response.status_code == 403

    # Remove Member Tests
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_remove_member_by_username(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Setup project and admin
        project = await create_project(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        admin = await create_user(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        await add_project_member(
            session=session, project=project, user=admin, project_role=ProjectRole.ADMIN
        )

        # Create user to remove
        user_to_remove = await create_user(
            session=session,
            name="removeuser",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        await add_project_member(
            session=session, project=project, user=user_to_remove, project_role=ProjectRole.USER
        )

        # Remove member
        body = {"usernames": ["removeuser"]}
        response = await client.post(
            f"/api/projects/{project.name}/remove_members",
            headers=get_auth_headers(admin.token),
            json=body,
        )

        assert response.status_code == 200
        response_data = response.json()

        # Check that user is NOT in the members list anymore
        member_usernames = [member["user"]["username"] for member in response_data["members"]]
        assert "removeuser" not in member_usernames

        # Verify removed from database
        res = await session.execute(
            select(MemberModel).where(MemberModel.user_id == user_to_remove.id)
        )
        member = res.scalar_one_or_none()
        assert member is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_remove_member_by_email(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Setup project and admin
        project = await create_project(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        admin = await create_user(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        await add_project_member(
            session=session, project=project, user=admin, project_role=ProjectRole.ADMIN
        )

        # Create user to remove
        user_to_remove = await create_user(
            session=session,
            name="emailremove",
            email="remove@example.com",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        await add_project_member(
            session=session, project=project, user=user_to_remove, project_role=ProjectRole.USER
        )

        # Remove member by email
        body = {"usernames": ["remove@example.com"]}
        response = await client.post(
            f"/api/projects/{project.name}/remove_members",
            headers=get_auth_headers(admin.token),
            json=body,
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_remove_member_errors_on_nonexistent_user(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Setup project and admin
        project = await create_project(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        admin = await create_user(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        await add_project_member(
            session=session, project=project, user=admin, project_role=ProjectRole.ADMIN
        )

        # Try to remove non-existent user - should now error instead of silently skipping
        body = {"usernames": ["nonexistent"]}
        response = await client.post(
            f"/api/projects/{project.name}/remove_members",
            headers=get_auth_headers(admin.token),
            json=body,
        )

        # Operation should fail with 400 error for non-existent user
        assert response.status_code == 400
        response_json = response.json()
        assert "User not found: nonexistent" in str(response_json)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_remove_member_errors_on_non_members(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Setup project and admin
        project = await create_project(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        admin = await create_user(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        await add_project_member(
            session=session, project=project, user=admin, project_role=ProjectRole.ADMIN
        )

        # Create user who is NOT a member
        _non_member = await create_user(
            session=session,
            name="nonmember",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )

        # Try to remove non-member - should now error instead of silently skipping
        body = {"usernames": ["nonmember"]}
        response = await client.post(
            f"/api/projects/{project.name}/remove_members",
            headers=get_auth_headers(admin.token),
            json=body,
        )

        # Operation should fail with 400 error for non-member
        assert response.status_code == 400
        response_json = response.json()
        assert "User is not a member of this project: nonmember" in str(response_json)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_remove_member_prevents_removing_last_admin(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Setup project with only one admin
        project = await create_project(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        admin = await create_user(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        await add_project_member(
            session=session, project=project, user=admin, project_role=ProjectRole.ADMIN
        )

        # Try to remove the only admin
        body = {"usernames": [admin.name]}
        response = await client.post(
            f"/api/projects/{project.name}/remove_members",
            headers=get_auth_headers(admin.token),
            json=body,
        )

        assert response.status_code == 400
        response_json = response.json()
        # Check for the new self-leave error message (since admin is removing themselves)
        assert "Cannot leave project: you are the last admin" in str(response_json)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_remove_member_requires_manager_or_admin_permission(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Setup project with regular user
        project = await create_project(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        admin = await create_user(
            session=session,
            name="admin",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        regular_user = await create_user(
            session=session,
            name="regular",
            global_role=GlobalRole.USER,
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        other_user = await create_user(
            session=session,
            name="other",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )

        await add_project_member(
            session=session, project=project, user=admin, project_role=ProjectRole.ADMIN
        )
        await add_project_member(
            session=session, project=project, user=regular_user, project_role=ProjectRole.USER
        )
        await add_project_member(
            session=session, project=project, user=other_user, project_role=ProjectRole.USER
        )

        # Try to remove as regular user
        body = {"usernames": ["other"]}
        response = await client.post(
            f"/api/projects/{project.name}/remove_members",
            headers=get_auth_headers(regular_user.token),
            json=body,
        )

        assert response.status_code == 403

    # Batch Operations Tests
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_add_multiple_members_batch(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Setup project and admin
        project = await create_project(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        admin = await create_user(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        await add_project_member(
            session=session, project=project, user=admin, project_role=ProjectRole.ADMIN
        )

        # Create multiple users to add
        _user1 = await create_user(
            session=session,
            name="user1",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        _user2 = await create_user(
            session=session,
            name="user2",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        _user3 = await create_user(
            session=session,
            name="user3",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )

        # Add multiple members at once
        body = {
            "members": [
                {"username": "user1", "project_role": "user"},
                {"username": "user2", "project_role": "manager"},
                {"username": "user3", "project_role": "user"},
            ]
        }
        response = await client.post(
            f"/api/projects/{project.name}/add_members",
            headers=get_auth_headers(admin.token),
            json=body,
        )

        assert response.status_code == 200
        response_data = response.json()

        # Check that all new users are in the members list
        member_usernames = [member["user"]["username"] for member in response_data["members"]]
        assert "user1" in member_usernames
        assert "user2" in member_usernames
        assert "user3" in member_usernames

        # Check roles
        user1_member = next(
            m for m in response_data["members"] if m["user"]["username"] == "user1"
        )
        assert user1_member["project_role"] == "user"

        user2_member = next(
            m for m in response_data["members"] if m["user"]["username"] == "user2"
        )
        assert user2_member["project_role"] == "manager"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_remove_multiple_members_batch(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Setup project and admin
        project = await create_project(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        admin = await create_user(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        await add_project_member(
            session=session, project=project, user=admin, project_role=ProjectRole.ADMIN
        )

        # Create multiple users to remove
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
        user3 = await create_user(
            session=session,
            name="user3",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )

        await add_project_member(
            session=session, project=project, user=user1, project_role=ProjectRole.USER
        )
        await add_project_member(
            session=session, project=project, user=user2, project_role=ProjectRole.USER
        )
        await add_project_member(
            session=session, project=project, user=user3, project_role=ProjectRole.USER
        )

        # Remove multiple members at once
        body = {"usernames": ["user1", "user2", "user3"]}
        response = await client.post(
            f"/api/projects/{project.name}/remove_members",
            headers=get_auth_headers(admin.token),
            json=body,
        )

        assert response.status_code == 200
        response_data = response.json()

        # Check that all users are NOT in the members list anymore
        member_usernames = [member["user"]["username"] for member in response_data["members"]]
        assert "user1" not in member_usernames
        assert "user2" not in member_usernames
        assert "user3" not in member_usernames

        # Verify removed from database
        res = await session.execute(select(MemberModel).where(MemberModel.user_id == user1.id))
        assert res.scalar_one_or_none() is None

        res = await session.execute(select(MemberModel).where(MemberModel.user_id == user2.id))
        assert res.scalar_one_or_none() is None

    # Join/Leave Functionality Tests
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_user_can_join_public_project(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Setup public project with admin
        project = await create_project(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        # Make project public
        project.is_public = True
        await session.commit()

        admin = await create_user(
            session=session,
            name="admin",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        await add_project_member(
            session=session, project=project, user=admin, project_role=ProjectRole.ADMIN
        )

        # Create user who wants to join
        regular_user = await create_user(
            session=session,
            name="joiner",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )

        # User joins public project (should work)
        body = {"members": [{"username": "joiner", "project_role": "user"}]}
        response = await client.post(
            f"/api/projects/{project.name}/add_members",
            headers=get_auth_headers(regular_user.token),
            json=body,
        )

        assert response.status_code == 200
        response_data = response.json()

        # Check that user is now in the members list
        member_usernames = [member["user"]["username"] for member in response_data["members"]]
        assert "joiner" in member_usernames

        # Find the new member and check their role is USER
        new_member = next(m for m in response_data["members"] if m["user"]["username"] == "joiner")
        assert new_member["project_role"] == "user"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_user_cannot_join_private_project(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Setup private project with admin
        project = await create_project(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        # Project is private by default (is_public=False)

        admin = await create_user(
            session=session,
            name="admin",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        await add_project_member(
            session=session, project=project, user=admin, project_role=ProjectRole.ADMIN
        )

        # Create user who wants to join
        regular_user = await create_user(
            session=session,
            name="joiner",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )

        # User tries to join private project (should fail)
        body = {"members": [{"username": "joiner", "project_role": "user"}]}
        response = await client.post(
            f"/api/projects/{project.name}/add_members",
            headers=get_auth_headers(regular_user.token),
            json=body,
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_user_cannot_join_public_project_as_admin(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Setup public project with admin
        project = await create_project(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        project.is_public = True
        await session.commit()

        admin = await create_user(
            session=session,
            name="admin",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        await add_project_member(
            session=session, project=project, user=admin, project_role=ProjectRole.ADMIN
        )

        # Create user who wants to join as admin
        regular_user = await create_user(
            session=session,
            name="joiner",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )

        # User tries to join public project as admin (should fail)
        body = {"members": [{"username": "joiner", "project_role": "admin"}]}
        response = await client.post(
            f"/api/projects/{project.name}/add_members",
            headers=get_auth_headers(regular_user.token),
            json=body,
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_user_can_leave_project(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Setup project with admin and regular member
        project = await create_project(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        admin = await create_user(
            session=session,
            name="admin",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        regular_user = await create_user(
            session=session,
            name="leaver",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )

        await add_project_member(
            session=session, project=project, user=admin, project_role=ProjectRole.ADMIN
        )
        await add_project_member(
            session=session, project=project, user=regular_user, project_role=ProjectRole.USER
        )

        # User leaves project (should work)
        body = {"usernames": ["leaver"]}
        response = await client.post(
            f"/api/projects/{project.name}/remove_members",
            headers=get_auth_headers(regular_user.token),
            json=body,
        )

        assert response.status_code == 200
        response_data = response.json()

        # Check that user is NOT in the members list anymore
        member_usernames = [member["user"]["username"] for member in response_data["members"]]
        assert "leaver" not in member_usernames

        # Should only have admin left
        assert len(response_data["members"]) == 1
        assert response_data["members"][0]["user"]["username"] == "admin"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_user_can_leave_project_by_email(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Setup project with admin and regular member
        project = await create_project(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        admin = await create_user(
            session=session,
            name="admin",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        regular_user = await create_user(
            session=session,
            name="leaver",
            email="leaver@example.com",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )

        await add_project_member(
            session=session, project=project, user=admin, project_role=ProjectRole.ADMIN
        )
        await add_project_member(
            session=session, project=project, user=regular_user, project_role=ProjectRole.USER
        )

        # User leaves project by email (should work)
        body = {"usernames": ["leaver@example.com"]}
        response = await client.post(
            f"/api/projects/{project.name}/remove_members",
            headers=get_auth_headers(regular_user.token),
            json=body,
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_last_admin_cannot_leave_project(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Setup project with only one admin
        project = await create_project(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        admin = await create_user(
            session=session,
            name="admin",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        await add_project_member(
            session=session, project=project, user=admin, project_role=ProjectRole.ADMIN
        )

        # Admin tries to leave (should fail as they're the last admin)
        body = {"usernames": ["admin"]}
        response = await client.post(
            f"/api/projects/{project.name}/remove_members",
            headers=get_auth_headers(admin.token),
            json=body,
        )

        assert response.status_code == 400
        response_json = response.json()
        assert "Cannot leave project: you are the last admin" in str(response_json)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_admin_can_leave_if_other_admins_exist(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Setup project with two admins
        project = await create_project(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        admin1 = await create_user(
            session=session,
            name="admin1",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        admin2 = await create_user(
            session=session,
            name="admin2",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )

        await add_project_member(
            session=session, project=project, user=admin1, project_role=ProjectRole.ADMIN
        )
        await add_project_member(
            session=session, project=project, user=admin2, project_role=ProjectRole.ADMIN
        )

        # One admin leaves (should work as there's another admin)
        body = {"usernames": ["admin1"]}
        response = await client.post(
            f"/api/projects/{project.name}/remove_members",
            headers=get_auth_headers(admin1.token),
            json=body,
        )

        assert response.status_code == 200
        response_data = response.json()

        # Check that admin1 is NOT in the members list anymore
        member_usernames = [member["user"]["username"] for member in response_data["members"]]
        assert "admin1" not in member_usernames
        assert "admin2" in member_usernames

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_user_cannot_leave_others_from_project(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Setup project with admin and two regular users
        project = await create_project(
            session=session, created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc)
        )
        admin = await create_user(
            session=session,
            name="admin",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
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

        await add_project_member(
            session=session, project=project, user=admin, project_role=ProjectRole.ADMIN
        )
        await add_project_member(
            session=session, project=project, user=user1, project_role=ProjectRole.USER
        )
        await add_project_member(
            session=session, project=project, user=user2, project_role=ProjectRole.USER
        )

        # user1 tries to remove user2 (should fail)
        body = {"usernames": ["user2"]}
        response = await client.post(
            f"/api/projects/{project.name}/remove_members",
            headers=get_auth_headers(user1.token),
            json=body,
        )

        assert response.status_code == 403
<<<<<<< HEAD
>>>>>>> 7fc1b408 (fix: retrack PR2 based on PR1)
=======


class TestUpdateProjectVisibility:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_40x_if_not_authenticated(self, test_db, client: AsyncClient):
        response = await client.post("/api/projects/test/update_visibility")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_404_if_project_does_not_exist(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session)
        response = await client.post(
            "/api/projects/nonexistent/update_visibility",
            headers=get_auth_headers(user.token),
            json={"is_public": True},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_project_admin_can_update_visibility(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Setup project with admin
        admin_user = await create_user(session=session, name="admin", global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=admin_user, is_public=False)
        await add_project_member(
            session=session, project=project, user=admin_user, project_role=ProjectRole.ADMIN
        )

        # Admin should be able to make project public
        response = await client.post(
            f"/api/projects/{project.name}/update_visibility",
            headers=get_auth_headers(admin_user.token),
            json={"is_public": True},
        )
        assert response.status_code == 200
        assert response.json()["is_public"] == True

        # Admin should be able to make project private again
        response = await client.post(
            f"/api/projects/{project.name}/update_visibility",
            headers=get_auth_headers(admin_user.token),
            json={"is_public": False},
        )
        assert response.status_code == 200
        assert response.json()["is_public"] == False

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_project_manager_can_update_visibility(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Setup project with admin and manager
        admin_user = await create_user(session=session, name="admin", global_role=GlobalRole.USER)
        manager_user = await create_user(
            session=session, name="manager", global_role=GlobalRole.USER
        )
        project = await create_project(session=session, owner=admin_user, is_public=False)
        await add_project_member(
            session=session, project=project, user=admin_user, project_role=ProjectRole.ADMIN
        )
        await add_project_member(
            session=session, project=project, user=manager_user, project_role=ProjectRole.MANAGER
        )

        # Manager should be able to update visibility
        response = await client.post(
            f"/api/projects/{project.name}/update_visibility",
            headers=get_auth_headers(manager_user.token),
            json={"is_public": True},
        )
        assert response.status_code == 200
        assert response.json()["is_public"] == True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_regular_user_cannot_update_visibility(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Setup project with admin and regular user
        admin_user = await create_user(session=session, name="admin", global_role=GlobalRole.USER)
        regular_user = await create_user(session=session, name="user", global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=admin_user, is_public=False)
        await add_project_member(
            session=session, project=project, user=admin_user, project_role=ProjectRole.ADMIN
        )
        await add_project_member(
            session=session, project=project, user=regular_user, project_role=ProjectRole.USER
        )

        # Regular user should not be able to update visibility
        response = await client.post(
            f"/api/projects/{project.name}/update_visibility",
            headers=get_auth_headers(regular_user.token),
            json={"is_public": True},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_non_member_cannot_update_visibility(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Setup project with admin and separate non-member user
        admin_user = await create_user(session=session, name="admin", global_role=GlobalRole.USER)
        non_member_user = await create_user(
            session=session, name="nonmember", global_role=GlobalRole.USER
        )
        project = await create_project(session=session, owner=admin_user, is_public=False)
        await add_project_member(
            session=session, project=project, user=admin_user, project_role=ProjectRole.ADMIN
        )

        # Non-member should not be able to update visibility
        response = await client.post(
            f"/api/projects/{project.name}/update_visibility",
            headers=get_auth_headers(non_member_user.token),
            json={"is_public": True},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_global_admin_can_update_any_project_visibility(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        # Setup project with regular owner and global admin
        project_owner = await create_user(
            session=session, name="owner", global_role=GlobalRole.USER
        )
        global_admin = await create_user(
            session=session, name="admin", global_role=GlobalRole.ADMIN
        )
        project = await create_project(session=session, owner=project_owner, is_public=False)
        await add_project_member(
            session=session, project=project, user=project_owner, project_role=ProjectRole.ADMIN
        )

        # Global admin should be able to update any project's visibility
        response = await client.post(
            f"/api/projects/{project.name}/update_visibility",
            headers=get_auth_headers(global_admin.token),
            json={"is_public": True},
        )
        assert response.status_code == 200
        assert response.json()["is_public"] == True
>>>>>>> a6246f4d (Add project visibility update API endpoint)
