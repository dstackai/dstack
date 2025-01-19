import datetime as dt
import uuid
from dataclasses import dataclass
from itertools import count

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.models import UserModel
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.testing.common import (
    create_fleet,
    create_instance,
    create_pool,
    create_project,
    create_user,
    get_auth_headers,
    get_fleet_configuration,
    get_fleet_spec,
)


@dataclass
class PreparedData:
    users: list[UserModel]


SAMPLE_FLEET_IDS = [uuid.uuid4() for _ in range(3)]


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestListInstances:
    @pytest_asyncio.fixture
    async def data(self, session: AsyncSession) -> PreparedData:
        users = [
            await create_user(session, name="user0", global_role=GlobalRole.ADMIN),
            await create_user(session, name="user1", global_role=GlobalRole.USER),
            await create_user(session, name="user2", global_role=GlobalRole.USER),
        ]
        projects = [
            await create_project(session, owner=users[0], name="project0"),
            await create_project(session, owner=users[1], name="project1"),
            await create_project(session, owner=users[2], name="project2"),
        ]
        await add_project_member(
            session, project=projects[0], user=users[0], project_role=ProjectRole.ADMIN
        )
        await add_project_member(
            session, project=projects[1], user=users[1], project_role=ProjectRole.ADMIN
        )
        await add_project_member(
            session, project=projects[2], user=users[2], project_role=ProjectRole.ADMIN
        )
        await add_project_member(
            session, project=projects[2], user=users[1], project_role=ProjectRole.USER
        )
        pools = [
            await create_pool(session, projects[0]),
            await create_pool(session, projects[1]),
            await create_pool(session, projects[2]),
        ]
        fleets = [
            await create_fleet(
                session,
                projects[0],
                spec=get_fleet_spec(conf=get_fleet_configuration("fleet0")),
                fleet_id=SAMPLE_FLEET_IDS[0],
            ),
            await create_fleet(
                session,
                projects[1],
                spec=get_fleet_spec(conf=get_fleet_configuration("fleet1")),
                fleet_id=SAMPLE_FLEET_IDS[1],
            ),
            await create_fleet(
                session,
                projects[2],
                spec=get_fleet_spec(conf=get_fleet_configuration("fleet2")),
                fleet_id=SAMPLE_FLEET_IDS[2],
            ),
        ]
        _ = [
            await create_instance(
                session=session,
                project=projects[0],
                pool=pools[0],
                fleet=fleets[0],
                created_at=dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc),
                name="fleet0-0",
            ),
            await create_instance(
                session=session,
                project=projects[1],
                pool=pools[1],
                fleet=fleets[1],
                created_at=dt.datetime(2024, 1, 2, tzinfo=dt.timezone.utc),
                name="fleet1-0",
            ),
            await create_instance(
                session=session,
                project=projects[2],
                pool=pools[2],
                fleet=fleets[2],
                created_at=dt.datetime(2024, 1, 3, tzinfo=dt.timezone.utc),
                name="fleet2-0",
            ),
            await create_instance(
                session=session,
                project=projects[2],
                pool=pools[2],
                fleet=fleets[2],
                created_at=dt.datetime(2024, 1, 4, tzinfo=dt.timezone.utc),
                instance_num=1,
                name="fleet2-1",
                status=InstanceStatus.TERMINATED,
            ),
        ]
        return PreparedData(users=users)

    @pytest.mark.parametrize(
        ("user", "expected_instances"),
        [
            pytest.param(
                0,
                ["fleet0-0", "fleet1-0", "fleet2-0", "fleet2-1"],
                id="global-admin",
            ),
            pytest.param(
                1,
                ["fleet1-0", "fleet2-0", "fleet2-1"],
                id="admin-in-one-project-user-in-other",
            ),
            pytest.param(
                2,
                ["fleet2-0", "fleet2-1"],
                id="project-admin",
            ),
        ],
    )
    async def test_project_access(
        self, user: int, expected_instances: list[str], data: PreparedData, client: AsyncClient
    ) -> None:
        resp = await client.post(
            "/api/instances/list",
            headers=get_auth_headers(data.users[user].token),
            json={"ascending": True},
        )
        assert resp.status_code == 200
        instances = [instance["name"] for instance in resp.json()]
        assert instances == expected_instances

    @pytest.mark.parametrize(
        ("filters", "expected_instances"),
        [
            pytest.param(
                {"project_names": ["project1", "project2"]},
                ["fleet1-0", "fleet2-0", "fleet2-1"],
                id="two-projects",
            ),
            pytest.param(
                {"project_names": ["project1"]},
                ["fleet1-0"],
                id="one-project",
            ),
            pytest.param(
                {"project_names": ["project0"]},
                [],
                id="forbidden-project",
            ),
            pytest.param(
                {"project_names": ["nonexistent"]},
                [],
                id="nonexistent-project",
            ),
            pytest.param(
                {"fleet_ids": [str(SAMPLE_FLEET_IDS[1]), str(SAMPLE_FLEET_IDS[2])]},
                ["fleet1-0", "fleet2-0", "fleet2-1"],
                id="two-fleets",
            ),
            pytest.param(
                {"fleet_ids": [str(SAMPLE_FLEET_IDS[1])]},
                ["fleet1-0"],
                id="one-fleet",
            ),
            pytest.param(
                {"fleet_ids": [str(SAMPLE_FLEET_IDS[0])]},
                [],
                id="forbidden-fleet",
            ),
            pytest.param(
                {"fleet_ids": [str(uuid.uuid4())]},
                [],
                id="nonexistent-fleet",
            ),
            pytest.param(
                {"project_names": ["project1"], "fleet_ids": [str(SAMPLE_FLEET_IDS[1])]},
                ["fleet1-0"],
                id="project-and-fleet-match",
            ),
            pytest.param(
                {"project_names": ["project2"], "fleet_ids": [str(SAMPLE_FLEET_IDS[1])]},
                [],
                id="project-and-fleet-no-match",
            ),
            pytest.param(
                {"only_active": True, "project_names": ["project2"]},
                ["fleet2-0"],
                id="only-active",
            ),
        ],
    )
    async def test_filters(
        self,
        filters: dict,
        expected_instances: list[str],
        data: PreparedData,
        client: AsyncClient,
    ) -> None:
        resp = await client.post(
            "/api/instances/list",
            headers=get_auth_headers(data.users[1].token),
            json={"ascending": True, **filters},
        )
        assert resp.status_code == 200
        instances = [instance["name"] for instance in resp.json()]
        assert instances == expected_instances

    @pytest.mark.parametrize(
        ("is_ascending", "expected_pages"),
        [
            pytest.param(True, [["fleet1-0", "fleet2-0"], ["fleet2-1"]], id="ascending"),
            pytest.param(False, [["fleet2-1", "fleet2-0"], ["fleet1-0"]], id="descending"),
        ],
    )
    async def test_pagination(
        self,
        is_ascending: bool,
        expected_pages: list[list[str]],
        data: PreparedData,
        client: AsyncClient,
    ) -> None:
        pages = []
        prev_id = None
        prev_created_at = None
        for page_no in count():
            if page_no == 10:
                raise RuntimeError("Too many pages")
            resp = await client.post(
                "/api/instances/list",
                headers=get_auth_headers(data.users[1].token),
                json={
                    "ascending": is_ascending,
                    "limit": 2,
                    "project_names": ["project1", "project2"],
                    "prev_id": prev_id,
                    "prev_created_at": prev_created_at,
                },
            )
            assert resp.status_code == 200
            page = []
            for instance in resp.json():
                page.append(instance["name"])
                prev_id = instance["id"]
                prev_created_at = instance["created"]
            if not page:
                break
            pages.append(page)
        assert pages == expected_pages

    async def test_not_authenticated(self, client: AsyncClient, data) -> None:
        resp = await client.post("/api/instances/list", json={})
        assert resp.status_code == 403
