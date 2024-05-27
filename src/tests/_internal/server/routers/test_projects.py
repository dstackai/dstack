import json
from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.main import app
from dstack._internal.server.models import MemberModel, ProjectModel
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.testing.common import (
    create_backend,
    create_project,
    create_user,
    get_auth_headers,
)

client = TestClient(app)


class TestListProjects:
    def test_returns_40x_if_not_authenticated(self):
        response = client.post("/api/projects/list")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_returns_empty_list(self, test_db, session: AsyncSession):
        user = await create_user(session=session)
        response = client.post("/api/projects/list", headers=get_auth_headers(user.token))
        assert response.status_code in [200]
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_returns_projects(self, test_db, session: AsyncSession):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        backend = await create_backend(
            session=session,
            project_id=project.id,
        )
        response = client.post("/api/projects/list", headers=get_auth_headers(user.token))
        assert response.status_code in [200]
        assert response.json() == [
            {
                "project_id": str(project.id),
                "project_name": project.name,
                "owner": {
                    "id": str(user.id),
                    "username": user.name,
                    "global_role": user.global_role,
                    "email": None,
                },
                "backends": [
                    {
                        "name": backend.type,
                        "config": {
                            "type": backend.type,
                            "regions": json.loads(backend.config)["regions"],
                            "vpc_name": None,
                            "vpc_ids": None,
                            "default_vpcs": None,
                            "public_ips": None,
                        },
                    }
                ],
                "members": [
                    {
                        "user": {
                            "id": str(user.id),
                            "username": user.name,
                            "global_role": user.global_role,
                            "email": None,
                        },
                        "project_role": ProjectRole.ADMIN,
                    }
                ],
            }
        ]


class TestCreateProject:
    def test_returns_40x_if_not_authenticated(self):
        response = client.post("/api/projects/create")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_creates_project(self, test_db, session: AsyncSession):
        user = await create_user(session=session)
        project_id = UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e")
        project_name = "test_project"
        body = {"project_name": project_name}
        with patch("uuid.uuid4") as m:
            m.return_value = project_id
            response = client.post(
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
                "global_role": user.global_role,
                "email": None,
            },
            "backends": [],
            "members": [
                {
                    "user": {
                        "id": str(user.id),
                        "username": user.name,
                        "global_role": user.global_role,
                        "email": None,
                    },
                    "project_role": ProjectRole.ADMIN,
                }
            ],
        }

    @pytest.mark.asyncio
    async def test_return_400_if_project_name_is_taken(self, test_db, session: AsyncSession):
        user = await create_user(session=session)
        with patch("uuid.uuid4") as m:
            m.return_value = UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e")
            response = client.post(
                "/api/projects/create",
                headers=get_auth_headers(user.token),
                json={"project_name": "TestProject"},
            )
        assert response.status_code == 200
        # Project name uniqueness check should be case insensitive
        for project_name in ["testproject", "TestProject", "TESTPROJECT"]:
            with patch("uuid.uuid4") as m:
                m.return_value = UUID("2b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e")
                response = client.post(
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
    async def test_returns_400_if_user_project_quota_exceeded(
        self, test_db, session: AsyncSession
    ):
        user = await create_user(session=session, name="owner", global_role=GlobalRole.USER)
        for i in range(10):
            response = client.post(
                "/api/projects/create",
                headers=get_auth_headers(user.token),
                json={"project_name": f"project{i}"},
            )
            assert response.status_code == 200, response.json()
        response = client.post(
            "/api/projects/create",
            headers=get_auth_headers(user.token),
            json={"project_name": "project11"},
        )
        assert response.status_code == 400
        assert response.json() == {
            "detail": [{"code": "error", "msg": "User project quota exceeded"}]
        }

    @pytest.mark.asyncio
    async def test_no_project_quota_for_global_admins(self, test_db, session: AsyncSession):
        user = await create_user(session=session, name="owner", global_role=GlobalRole.ADMIN)
        for i in range(12):
            response = client.post(
                "/api/projects/create",
                headers=get_auth_headers(user.token),
                json={"project_name": f"project{i}"},
            )
            assert response.status_code == 200, response.json()


class TestDeleteProject:
    def test_returns_40x_if_not_authenticated(self):
        response = client.post("/api/projects/delete")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_cannot_delete_the_only_project(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        response = client.post(
            "/api/projects/delete",
            headers=get_auth_headers(user.token),
            json={"projects_names": [project.name]},
        )
        assert response.status_code == 400
        await session.refresh(project)
        assert not project.deleted

    @pytest.mark.asyncio
    async def test_deletes_projects(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project1 = await create_project(session=session, owner=user, name="project1")
        await add_project_member(
            session=session, project=project1, user=user, project_role=ProjectRole.ADMIN
        )
        project2 = await create_project(session=session, owner=user, name="project2")
        await add_project_member(
            session=session, project=project2, user=user, project_role=ProjectRole.ADMIN
        )
        response = client.post(
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
    async def test_returns_403_if_not_project_admin(self, test_db, session: AsyncSession):
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
        response = client.post(
            "/api/projects/delete",
            headers=get_auth_headers(user.token),
            json={"projects_names": [project1.name, project2.name]},
        )
        assert response.status_code == 403
        res = await session.execute(select(ProjectModel))
        assert len(res.all()) == 2

    @pytest.mark.asyncio
    async def test_returns_403_if_not_project_member(self, test_db, session: AsyncSession):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, name="project")
        response = client.post(
            "/api/projects/delete",
            headers=get_auth_headers(user.token),
            json={"projects_names": [project.name]},
        )
        assert response.status_code == 403
        res = await session.execute(select(ProjectModel))
        assert len(res.all()) == 1


class TestGetProject:
    def test_returns_40x_if_not_authenticated(self):
        response = client.post("/api/projects/test_project/get")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_returns_404_if_project_does_not_exist(self, test_db, session: AsyncSession):
        user = await create_user(session=session)
        response = client.post(
            "/api/projects/test_project/get",
            headers=get_auth_headers(user.token),
        )
        assert response.status_code == 404, response.json()

    @pytest.mark.asyncio
    async def test_returns_project(self, test_db, session: AsyncSession):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        response = client.post(
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
                "global_role": user.global_role,
                "email": None,
            },
            "backends": [],
            "members": [
                {
                    "user": {
                        "id": str(user.id),
                        "username": user.name,
                        "global_role": user.global_role,
                        "email": None,
                    },
                    "project_role": ProjectRole.ADMIN,
                }
            ],
        }


class TestSetProjectMembers:
    def test_returns_40x_if_not_authenticated(self):
        response = client.post("/api/projects/test_project/get")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_sets_project_members(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        admin = await create_user(session=session)
        await add_project_member(
            session=session, project=project, user=admin, project_role=ProjectRole.ADMIN
        )
        user1 = await create_user(session=session, name="user1")
        user2 = await create_user(session=session, name="user2")
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
        response = client.post(
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
                    "global_role": admin.global_role,
                    "email": None,
                },
                "project_role": ProjectRole.ADMIN,
            },
            {
                "user": {
                    "id": str(user1.id),
                    "username": user1.name,
                    "global_role": user1.global_role,
                    "email": None,
                },
                "project_role": ProjectRole.ADMIN,
            },
            {
                "user": {
                    "id": str(user2.id),
                    "username": user2.name,
                    "global_role": user2.global_role,
                    "email": None,
                },
                "project_role": ProjectRole.USER,
            },
        ]
        res = await session.execute(select(MemberModel))
        members = res.scalars().all()
        assert len(members) == 3
