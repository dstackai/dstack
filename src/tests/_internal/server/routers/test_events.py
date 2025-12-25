import uuid
from datetime import datetime
from unittest.mock import patch

import pytest
from freezegun import freeze_time
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.services import events
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.testing.common import (
    create_fleet,
    create_instance,
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_auth_headers,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.usefixtures("test_db", "image_config_mock"),
    pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True),
]


class TestListEventsGeneral:
    async def test_response_format(self, session: AsyncSession, client: AsyncClient) -> None:
        user = await create_user(session=session, name="test_user")
        project = await create_project(session=session, owner=user, name="test_project")
        await add_project_member(
            session=session,
            project=project,
            user=user,
            project_role=ProjectRole.ADMIN,
        )
        event_ids = [uuid.uuid4() for _ in range(2)]
        with patch("uuid.uuid4", side_effect=event_ids):
            with freeze_time(datetime(2026, 1, 1, 12, 0, 0)):
                events.emit(
                    session,
                    "User added to project",
                    actor=events.UserActor.from_user(user),
                    targets=[events.Target.from_model(user), events.Target.from_model(project)],
                )
            with freeze_time(datetime(2026, 1, 1, 12, 0, 1)):
                events.emit(
                    session,
                    "Project updated",
                    actor=events.SystemActor(),
                    targets=[events.Target.from_model(project)],
                )
        await session.commit()

        resp = await client.post("/api/events/list", headers=get_auth_headers(user.token), json={})
        resp.raise_for_status()
        resp_data = resp.json()
        for event in resp_data:
            event["targets"].sort(key=lambda t: t["type"])  # for consistent comparison
        assert resp_data == [
            {
                "id": str(event_ids[1]),
                "message": "Project updated",
                "recorded_at": "2026-01-01T12:00:01+00:00",
                "actor_user_id": None,
                "actor_user": None,
                "is_actor_user_deleted": None,
                "targets": [
                    {
                        "type": "project",
                        "project_id": str(project.id),
                        "project_name": "test_project",
                        "is_project_deleted": False,
                        "id": str(project.id),
                        "name": "test_project",
                    },
                ],
            },
            {
                "id": str(event_ids[0]),
                "message": "User added to project",
                "recorded_at": "2026-01-01T12:00:00+00:00",
                "actor_user_id": str(user.id),
                "actor_user": "test_user",
                "is_actor_user_deleted": False,
                "targets": [
                    {
                        "type": "project",
                        "project_id": str(project.id),
                        "project_name": "test_project",
                        "is_project_deleted": False,
                        "id": str(project.id),
                        "name": "test_project",
                    },
                    {
                        "type": "user",
                        "project_id": None,
                        "project_name": None,
                        "is_project_deleted": None,
                        "id": str(user.id),
                        "name": "test_user",
                    },
                ],
            },
        ]

    async def test_deleted_actor_and_project(
        self, session: AsyncSession, client: AsyncClient
    ) -> None:
        user = await create_user(session=session, name="test_user")
        project = await create_project(session=session, owner=user, name="test_project")
        events.emit(
            session,
            "Project deleted",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(project)],
        )
        user.original_name = user.name
        user.name = "_deleted_user_placeholder"
        user.deleted = True
        project.original_name = project.name
        project.name = "_deleted_project_placeholder"
        project.deleted = True
        await session.commit()
        other_user = await create_user(session=session, name="other_user")

        resp = await client.post(
            "/api/events/list", headers=get_auth_headers(other_user.token), json={}
        )
        resp.raise_for_status()
        assert len(resp.json()) == 1
        assert resp.json()[0]["actor_user_id"] == str(user.id)
        assert resp.json()[0]["actor_user"] == "test_user"
        assert resp.json()[0]["is_actor_user_deleted"] == True
        assert len(resp.json()[0]["targets"]) == 1
        assert resp.json()[0]["targets"][0]["project_id"] == str(project.id)
        assert resp.json()[0]["targets"][0]["project_name"] == "test_project"
        assert resp.json()[0]["targets"][0]["is_project_deleted"] == True

    async def test_empty_response_when_no_events(
        self, session: AsyncSession, client: AsyncClient
    ) -> None:
        user = await create_user(session=session)
        resp = await client.post("/api/events/list", headers=get_auth_headers(user.token), json={})
        resp.raise_for_status()
        assert resp.json() == []


class TestListEventsAccessControl:
    async def test_user_sees_events_about_themselves(
        self, session: AsyncSession, client: AsyncClient
    ) -> None:
        admin_user = await create_user(
            session=session,
            name="admin",
            global_role=GlobalRole.ADMIN,
        )
        regular_user = await create_user(
            session=session,
            name="regular",
            global_role=GlobalRole.USER,
        )
        events.emit(
            session,
            "User created",
            actor=events.UserActor.from_user(admin_user),
            targets=[events.Target.from_model(admin_user)],
        )
        events.emit(
            session,
            "User created",
            actor=events.UserActor.from_user(admin_user),
            targets=[events.Target.from_model(regular_user)],
        )
        await session.commit()

        # Regular user only sees the event about themselves
        resp = await client.post(
            "/api/events/list", headers=get_auth_headers(regular_user.token), json={}
        )
        resp.raise_for_status()
        assert len(resp.json()) == 1
        assert resp.json()[0]["targets"][0]["id"] == str(regular_user.id)

        # Admin sees all events
        resp = await client.post(
            "/api/events/list", headers=get_auth_headers(admin_user.token), json={}
        )
        resp.raise_for_status()
        assert len(resp.json()) == 2

    async def test_user_sees_events_within_their_project(
        self, session: AsyncSession, client: AsyncClient
    ) -> None:
        admin_user = await create_user(
            session=session,
            name="admin",
            global_role=GlobalRole.ADMIN,
        )
        regular_user = await create_user(
            session=session,
            name="regular",
            global_role=GlobalRole.USER,
        )
        admin_project = await create_project(
            session=session,
            name="admin",
            owner=admin_user,
        )
        regular_project = await create_project(
            session=session,
            name="regular",
            owner=regular_user,
        )
        await add_project_member(
            session=session,
            project=admin_project,
            user=admin_user,
            project_role=ProjectRole.ADMIN,
        )
        await add_project_member(
            session=session,
            project=regular_project,
            user=regular_user,
            project_role=ProjectRole.USER,
        )
        admin_fleet = await create_fleet(
            session=session,
            project=admin_project,
            name="admin",
        )
        regular_fleet = await create_fleet(
            session=session,
            project=regular_project,
            name="regular",
        )
        events.emit(
            session,
            "Project created",
            actor=events.UserActor.from_user(admin_user),
            targets=[events.Target.from_model(admin_project)],
        )
        events.emit(
            session,
            "Project created",
            actor=events.UserActor.from_user(admin_user),
            targets=[events.Target.from_model(regular_project)],
        )
        events.emit(
            session,
            "Fleet created",
            actor=events.UserActor.from_user(admin_user),
            targets=[events.Target.from_model(admin_fleet)],
        )
        events.emit(
            session,
            "Fleet created",
            actor=events.UserActor.from_user(admin_user),
            targets=[events.Target.from_model(regular_fleet)],
        )
        await session.commit()

        # Regular user only sees the events within their project
        resp = await client.post(
            "/api/events/list", headers=get_auth_headers(regular_user.token), json={}
        )
        resp.raise_for_status()
        assert len(resp.json()) == 2
        assert {resp.json()[0]["targets"][0]["id"], resp.json()[1]["targets"][0]["id"]} == {
            str(regular_project.id),
            str(regular_fleet.id),
        }

        # Admin sees all events
        resp = await client.post(
            "/api/events/list", headers=get_auth_headers(admin_user.token), json={}
        )
        resp.raise_for_status()
        assert len(resp.json()) == 4

    async def test_filters_do_not_bypass_access_control(
        self, session: AsyncSession, client: AsyncClient
    ) -> None:
        admin = await create_user(
            session=session,
            name="admin",
            global_role=GlobalRole.ADMIN,
        )
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session)
        fleet = await create_fleet(session=session, project=project)
        events.emit(
            session,
            "Project created",
            actor=events.UserActor.from_user(admin),
            targets=[events.Target.from_model(project)],
        )
        events.emit(
            session,
            "Fleet created",
            actor=events.UserActor.from_user(admin),
            targets=[events.Target.from_model(fleet)],
        )
        await session.commit()

        # Regular user can't see events from a project they are not a member of
        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"within_projects": [str(project.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 0
        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"target_projects": [str(project.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 0
        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"target_fleets": [str(fleet.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 0

        # Admin can see the events
        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(admin.token),
            json={"within_projects": [str(project.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 2
        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(admin.token),
            json={"target_projects": [str(project.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 1
        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(admin.token),
            json={"target_fleets": [str(fleet.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 1


class TestListEventsFilters:
    async def test_target_projects(self, session: AsyncSession, client: AsyncClient) -> None:
        user = await create_user(session=session)
        project_a = await create_project(session=session, name="project_a", owner=user)
        project_b = await create_project(session=session, name="project_b", owner=user)
        fleet_a = await create_fleet(session=session, project=project_a)
        events.emit(
            session,
            "User created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(user)],
        )
        events.emit(
            session,
            "Project created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(project_a)],
        )
        events.emit(
            session,
            "Project created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(project_b)],
        )
        events.emit(
            session,
            "Fleet created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(fleet_a)],
        )
        await session.commit()

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"target_projects": [str(project_a.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 1
        assert resp.json()[0]["targets"][0]["id"] == str(project_a.id)

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"target_projects": [str(project_b.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 1
        assert resp.json()[0]["targets"][0]["id"] == str(project_b.id)

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"target_projects": [str(project_a.id), str(project_b.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 2

    async def test_target_users(self, session: AsyncSession, client: AsyncClient) -> None:
        user_a = await create_user(session=session, name="user_a")
        user_b = await create_user(session=session, name="user_b")
        project_a = await create_project(session=session, name="project_a", owner=user_a)
        events.emit(
            session,
            "User created",
            actor=events.UserActor.from_user(user_a),
            targets=[events.Target.from_model(user_a)],
        )
        events.emit(
            session,
            "User created",
            actor=events.UserActor.from_user(user_b),
            targets=[events.Target.from_model(user_b)],
        )
        events.emit(
            session,
            "Project created",
            actor=events.UserActor.from_user(user_a),
            targets=[events.Target.from_model(project_a)],
        )
        await session.commit()

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user_a.token),
            json={"target_users": [str(user_a.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 1
        assert resp.json()[0]["targets"][0]["id"] == str(user_a.id)

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user_b.token),
            json={"target_users": [str(user_b.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 1
        assert resp.json()[0]["targets"][0]["id"] == str(user_b.id)

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user_a.token),
            json={"target_users": [str(user_a.id), str(user_b.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 2

    async def test_target_fleets(self, session: AsyncSession, client: AsyncClient) -> None:
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        fleet_a = await create_fleet(
            session=session,
            project=project,
            name="fleet_a",
        )
        fleet_b = await create_fleet(
            session=session,
            project=project,
            name="fleet_b",
        )
        instance_a = await create_instance(
            session=session,
            project=project,
            fleet=fleet_a,
        )
        events.emit(
            session,
            "Fleet created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(fleet_a)],
        )
        events.emit(
            session,
            "Fleet created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(fleet_b)],
        )
        events.emit(
            session,
            "Instance created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(instance_a)],
        )
        await session.commit()

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"target_fleets": [str(fleet_a.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 1
        assert resp.json()[0]["targets"][0]["id"] == str(fleet_a.id)

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"target_fleets": [str(fleet_b.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 1
        assert resp.json()[0]["targets"][0]["id"] == str(fleet_b.id)

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"target_fleets": [str(fleet_a.id), str(fleet_b.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 2

    async def test_target_instances(self, session: AsyncSession, client: AsyncClient) -> None:
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        fleet = await create_fleet(session=session, project=project)
        instance_a = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
        )
        instance_b = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
        )
        events.emit(
            session,
            "Fleet created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(fleet)],
        )
        events.emit(
            session,
            "Instance created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(instance_a)],
        )
        events.emit(
            session,
            "Instance created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(instance_b)],
        )
        await session.commit()

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"target_instances": [str(instance_a.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 1
        assert resp.json()[0]["targets"][0]["id"] == str(instance_a.id)

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"target_instances": [str(instance_b.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 1
        assert resp.json()[0]["targets"][0]["id"] == str(instance_b.id)

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"target_instances": [str(instance_a.id), str(instance_b.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 2

    async def test_target_runs(self, session: AsyncSession, client: AsyncClient) -> None:
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(session=session, project_id=project.id)
        run_a = await create_run(
            session=session,
            project=project,
            run_name="run_a",
            repo=repo,
            user=user,
        )
        run_b = await create_run(
            session=session,
            project=project,
            run_name="run_b",
            repo=repo,
            user=user,
        )
        job_a = await create_job(
            session=session,
            run=run_a,
        )
        events.emit(
            session,
            "Run created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(run_a)],
        )
        events.emit(
            session,
            "Run created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(run_b)],
        )
        events.emit(
            session,
            "Job created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(job_a)],
        )
        await session.commit()

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"target_runs": [str(run_a.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 1
        assert resp.json()[0]["targets"][0]["id"] == str(run_a.id)

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"target_runs": [str(run_b.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 1
        assert resp.json()[0]["targets"][0]["id"] == str(run_b.id)

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"target_runs": [str(run_a.id), str(run_b.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 2

    async def test_target_jobs(self, session: AsyncSession, client: AsyncClient) -> None:
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(
            session=session,
            project=project,
            run_name="run",
            repo=repo,
            user=user,
        )
        job_a = await create_job(
            session=session,
            run=run,
        )
        job_b = await create_job(
            session=session,
            run=run,
        )
        events.emit(
            session,
            "Run created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(run)],
        )
        events.emit(
            session,
            "Job created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(job_a)],
        )
        events.emit(
            session,
            "Job created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(job_b)],
        )
        await session.commit()

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"target_jobs": [str(job_a.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 1
        assert resp.json()[0]["targets"][0]["id"] == str(job_a.id)

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"target_jobs": [str(job_b.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 1
        assert resp.json()[0]["targets"][0]["id"] == str(job_b.id)

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"target_jobs": [str(job_a.id), str(job_b.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 2

    async def test_within_projects(self, session: AsyncSession, client: AsyncClient) -> None:
        user = await create_user(session=session)
        project_a = await create_project(session=session, name="project_a", owner=user)
        project_b = await create_project(session=session, name="project_b", owner=user)
        fleet_a = await create_fleet(session=session, project=project_a)
        instance_a = await create_instance(
            session=session,
            project=project_a,
            fleet=fleet_a,
        )
        events.emit(
            session,
            "User created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(user)],
        )
        events.emit(
            session,
            "Project created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(project_a)],
        )
        events.emit(
            session,
            "Project created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(project_b)],
        )
        events.emit(
            session,
            "Fleet created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(fleet_a)],
        )
        events.emit(
            session,
            "Instance created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(instance_a)],
        )
        await session.commit()

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"within_projects": [str(project_a.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 3

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"within_projects": [str(project_b.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 1

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"within_projects": [str(project_a.id), str(project_b.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 4

    async def test_within_fleets(self, session: AsyncSession, client: AsyncClient) -> None:
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        fleet_a = await create_fleet(
            session=session,
            project=project,
            name="fleet_a",
        )
        fleet_b = await create_fleet(
            session=session,
            project=project,
            name="fleet_b",
        )
        isinstance_a = await create_instance(
            session=session,
            project=project,
            fleet=fleet_a,
        )
        events.emit(
            session,
            "Project created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(project)],
        )
        events.emit(
            session,
            "Fleet created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(fleet_a)],
        )
        events.emit(
            session,
            "Fleet created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(fleet_b)],
        )
        events.emit(
            session,
            "Instance created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(isinstance_a)],
        )
        await session.commit()

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"within_fleets": [str(fleet_a.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 2

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"within_fleets": [str(fleet_b.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 1

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"within_fleets": [str(fleet_a.id), str(fleet_b.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 3

    async def test_within_runs(self, session: AsyncSession, client: AsyncClient) -> None:
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(session=session, project_id=project.id)
        run_a = await create_run(
            session=session,
            project=project,
            run_name="run_a",
            repo=repo,
            user=user,
        )
        run_b = await create_run(
            session=session,
            project=project,
            run_name="run_b",
            repo=repo,
            user=user,
        )
        job_a = await create_job(
            session=session,
            run=run_a,
        )
        events.emit(
            session,
            "Project created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(project)],
        )
        events.emit(
            session,
            "Run created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(run_a)],
        )
        events.emit(
            session,
            "Run created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(run_b)],
        )
        events.emit(
            session,
            "Job created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(job_a)],
        )
        await session.commit()

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"within_runs": [str(run_a.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 2

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"within_runs": [str(run_b.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 1

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"within_runs": [str(run_a.id), str(run_b.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 3

    async def test_include_target_types(self, session: AsyncSession, client: AsyncClient) -> None:
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        fleet = await create_fleet(session=session, project=project)
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
        )
        events.emit(
            session,
            "Project created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(project)],
        )
        events.emit(
            session,
            "Fleet created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(fleet)],
        )
        events.emit(
            session,
            "Instance created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(instance)],
        )
        await session.commit()

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"include_target_types": ["fleet"]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 1
        assert resp.json()[0]["targets"][0]["type"] == "fleet"

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"include_target_types": ["instance"]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 1
        assert resp.json()[0]["targets"][0]["type"] == "instance"

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"include_target_types": ["project", "fleet"]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 2
        assert {resp.json()[0]["targets"][0]["type"], resp.json()[1]["targets"][0]["type"]} == {
            "project",
            "fleet",
        }

    async def test_within_projects_and_include_target_types(
        self, session: AsyncSession, client: AsyncClient
    ) -> None:
        user = await create_user(session=session)
        project_a = await create_project(session=session, name="project_a", owner=user)
        project_b = await create_project(session=session, name="project_b", owner=user)
        fleet_a = await create_fleet(session=session, project=project_a)
        instance_a = await create_instance(
            session=session,
            project=project_a,
            fleet=fleet_a,
        )
        fleet_b = await create_fleet(session=session, project=project_b)
        instance_b = await create_instance(
            session=session,
            project=project_b,
            fleet=fleet_b,
        )
        events.emit(
            session,
            "Project created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(project_a)],
        )
        events.emit(
            session,
            "Fleet created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(fleet_a)],
        )
        events.emit(
            session,
            "Instance created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(instance_a)],
        )
        events.emit(
            session,
            "Project created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(project_b)],
        )
        events.emit(
            session,
            "Fleet created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(fleet_b)],
        )
        events.emit(
            session,
            "Instance created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(instance_b)],
        )
        await session.commit()

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={
                "within_projects": [str(project_a.id)],
                "include_target_types": ["fleet"],
            },
        )
        resp.raise_for_status()
        assert len(resp.json()) == 1
        assert resp.json()[0]["targets"][0]["type"] == "fleet"
        assert resp.json()[0]["targets"][0]["id"] == str(fleet_a.id)

    async def test_actors(self, session: AsyncSession, client: AsyncClient) -> None:
        user_a = await create_user(session=session, name="user_a")
        user_b = await create_user(session=session, name="user_b")
        project_a = await create_project(session=session, owner=user_a, name="project_a")
        project_b = await create_project(session=session, owner=user_b, name="project_b")
        events.emit(
            session,
            "Project created",
            actor=events.UserActor.from_user(user_a),
            targets=[events.Target.from_model(project_a)],
        )
        events.emit(
            session,
            "Project created",
            actor=events.UserActor.from_user(user_b),
            targets=[events.Target.from_model(project_b)],
        )
        events.emit(
            session,
            "Project updated",
            actor=events.SystemActor(),
            targets=[events.Target.from_model(project_a)],
        )
        await session.commit()

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user_a.token),
            json={"actors": [str(user_a.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 1
        assert resp.json()[0]["message"] == "Project created"
        assert resp.json()[0]["targets"][0]["id"] == str(project_a.id)

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user_a.token),
            json={"actors": [str(user_b.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 1
        assert resp.json()[0]["message"] == "Project created"
        assert resp.json()[0]["targets"][0]["id"] == str(project_b.id)

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user_a.token),
            json={"actors": [None]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 1
        assert resp.json()[0]["message"] == "Project updated"
        assert resp.json()[0]["targets"][0]["id"] == str(project_a.id)

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user_a.token),
            json={"actors": [str(user_a.id), None]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 2
        assert {resp.json()[0]["targets"][0]["id"], resp.json()[1]["targets"][0]["id"]} == {
            str(project_a.id)
        }

    async def test_event_included_if_at_least_one_target_is_within_filters(
        self, session: AsyncSession, client: AsyncClient
    ) -> None:
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        fleet = await create_fleet(session=session, project=project)
        instance_a = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
        )
        instance_b = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
        )
        events.emit(
            session,
            "Fleet instances created",
            actor=events.UserActor.from_user(user),
            targets=[
                events.Target.from_model(instance_a),
                events.Target.from_model(instance_b),
            ],
        )
        instance_c = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
        )
        events.emit(
            session,
            "Instance created",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(instance_c)],
        )
        await session.commit()

        for target_instances in [[instance_a.id], [instance_b.id], [instance_a.id, instance_b.id]]:
            resp = await client.post(
                "/api/events/list",
                headers=get_auth_headers(user.token),
                json={"target_instances": list(map(str, target_instances))},
            )
            resp.raise_for_status()
            assert len(resp.json()) == 1
            assert resp.json()[0]["message"] == "Fleet instances created"
            assert len(resp.json()[0]["targets"]) == 2

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"target_instances": [str(instance_c.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 1
        assert resp.json()[0]["message"] == "Instance created"
        assert len(resp.json()[0]["targets"]) == 1

        resp = await client.post(
            "/api/events/list",
            headers=get_auth_headers(user.token),
            json={"target_instances": [str(instance_a.id), str(instance_c.id)]},
        )
        resp.raise_for_status()
        assert len(resp.json()) == 2


class TestListEventsPagination:
    @pytest.mark.parametrize("ascending", [True, False])
    async def test_pagination(
        self, session: AsyncSession, client: AsyncClient, ascending: bool
    ) -> None:
        users = []
        for i in range(5):
            user = await create_user(session=session, name=f"user_{i}")
            users.append(user)
            with freeze_time(datetime(2026, 1, 1, 12, 0, 0, i)):
                events.emit(
                    session,
                    "User created",
                    actor=events.UserActor.from_user(user),
                    targets=[events.Target.from_model(user)],
                )
        await session.commit()

        if not ascending:
            users.reverse()

        resp = await client.post(
            "/api/events/list",
            json={
                "limit": 2,
                "ascending": ascending,
            },
            headers=get_auth_headers(users[0].token),
        )
        resp.raise_for_status()
        assert len(resp.json()) == 2
        assert resp.json()[0]["targets"][0]["name"] == users[0].name
        assert resp.json()[1]["targets"][0]["name"] == users[1].name

        resp = await client.post(
            "/api/events/list",
            json={
                "limit": 2,
                "ascending": ascending,
                "prev_id": resp.json()[-1]["id"],
                "prev_recorded_at": resp.json()[-1]["recorded_at"],
            },
            headers=get_auth_headers(users[0].token),
        )
        resp.raise_for_status()
        assert len(resp.json()) == 2
        assert resp.json()[0]["targets"][0]["name"] == users[2].name
        assert resp.json()[1]["targets"][0]["name"] == users[3].name

        resp = await client.post(
            "/api/events/list",
            json={
                "limit": 2,
                "ascending": ascending,
                "prev_id": resp.json()[-1]["id"],
                "prev_recorded_at": resp.json()[-1]["recorded_at"],
            },
            headers=get_auth_headers(users[0].token),
        )
        resp.raise_for_status()
        assert len(resp.json()) == 1
        assert resp.json()[0]["targets"][0]["name"] == users[4].name

        resp = await client.post(
            "/api/events/list",
            json={
                "limit": 2,
                "ascending": ascending,
                "prev_id": resp.json()[-1]["id"],
                "prev_recorded_at": resp.json()[-1]["recorded_at"],
            },
            headers=get_auth_headers(users[0].token),
        )
        resp.raise_for_status()
        assert len(resp.json()) == 0

    async def test_limits_events_regardless_number_of_targets(
        self, session: AsyncSession, client: AsyncClient
    ) -> None:
        users = [await create_user(session=session, name=f"user_{i}") for i in range(3)]
        with freeze_time(datetime(2026, 1, 1, 12, 0, 0, 0)):
            events.emit(
                session,
                "Users batch created",
                actor=events.SystemActor(),
                targets=[events.Target.from_model(users[0]), events.Target.from_model(users[1])],
            )
        with freeze_time(datetime(2026, 1, 1, 12, 0, 0, 1)):
            events.emit(
                session,
                "User created",
                actor=events.SystemActor(),
                targets=[events.Target.from_model(users[2])],
            )
        await session.commit()

        resp = await client.post(
            "/api/events/list",
            json={
                "limit": 1,
                "ascending": True,
            },
            headers=get_auth_headers(users[0].token),
        )
        resp.raise_for_status()
        assert len(resp.json()) == 1
        assert resp.json()[0]["message"] == "Users batch created"
        assert len(resp.json()[0]["targets"]) == 2
        assert {resp.json()[0]["targets"][0]["id"], resp.json()[0]["targets"][1]["id"]} == {
            str(users[0].id),
            str(users[1].id),
        }

        resp = await client.post(
            "/api/events/list",
            json={
                "limit": 1,
                "ascending": True,
                "prev_id": resp.json()[-1]["id"],
                "prev_recorded_at": resp.json()[-1]["recorded_at"],
            },
            headers=get_auth_headers(users[0].token),
        )
        resp.raise_for_status()
        assert len(resp.json()) == 1
        assert resp.json()[0]["message"] == "User created"
        assert len(resp.json()[0]["targets"]) == 1
        assert resp.json()[0]["targets"][0]["id"] == str(users[2].id)

        resp = await client.post(
            "/api/events/list",
            json={
                "limit": 2,
                "ascending": True,
            },
            headers=get_auth_headers(users[0].token),
        )
        resp.raise_for_status()
        assert len(resp.json()) == 2
