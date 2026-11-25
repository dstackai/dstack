import uuid
from typing import Optional
from unittest.mock import AsyncMock

import httpx2 as httpx
import pytest
import pytest_asyncio
from aiocache.base import BaseCache

from dstack._internal.core.models.projects import Member, MemberPermissions, Project
from dstack._internal.core.models.users import GlobalRole, ProjectRole, User, UserPermissions
from dstack._internal.proxy.gateway.auth import GatewayProxyAuthProvider
from dstack._internal.proxy.gateway.services.server_client import HTTPMultiClient
from dstack._internal.proxy.lib.auth import ProxyCaller
from dstack._internal.proxy.lib.errors import ProxyError, UnexpectedProxyError


@pytest_asyncio.fixture(autouse=True)
async def clear_auth_cache():
    caches = [
        _get_auth_cache(),
        _get_cache(GatewayProxyAuthProvider._get_user_id),
        _get_cache(GatewayProxyAuthProvider._is_global_admin),
    ]
    for cache in caches:
        await cache.clear()
    yield
    for cache in caches:
        await cache.clear()


def make_user(global_role: GlobalRole = GlobalRole.USER) -> User:
    return User(
        id=uuid.uuid4(),
        username="test-user",
        global_role=global_role,
        active=True,
        permissions=UserPermissions(can_create_projects=True),
    )


def make_project(members: Optional[list[User]] = None) -> Project:
    owner = make_user()
    return Project(
        project_id=uuid.uuid4(),
        project_name="test",
        owner=owner,
        backends=[],
        members=[
            Member(
                user=user,
                project_role=ProjectRole.USER,
                permissions=MemberPermissions(can_manage_ssh_fleets=True),
            )
            for user in [owner, *(members or [])]
        ],
    )


@pytest.mark.asyncio
class TestGatewayProxyAuthProvider:
    @pytest.mark.parametrize("status", [200, 403, 404])
    async def test_caches_project_token_decision_for_sixty_seconds(self, monkeypatch, status):
        requests = []

        def handle(request):
            requests.append(request)
            return httpx.Response(status, content=make_project().model_dump_json())

        cache = _get_auth_cache()
        set_value = AsyncMock(wraps=cache.set)
        monkeypatch.setattr(cache, "set", set_value)
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handle), base_url="http://dstack/"
        ) as client:
            provider = GatewayProxyAuthProvider(client)
            for _ in range(2):
                assert await provider.is_project_member("first", "token") is (status == 200)
            assert len(requests) == 1
            assert requests[0].method == "POST"
            assert requests[0].url.path == "/api/projects/first/get"
            assert requests[0].headers["Authorization"] == "Bearer token"
            assert set_value.call_args.kwargs["ttl"] == 60

            # Different tokens and projects must not inherit another cached decision.
            await provider.is_project_member("first", "other-token")
            await provider.is_project_member("second", "token")
            assert len(requests) == 3

    @pytest.mark.parametrize("failure", [500, httpx.ReadTimeout])
    async def test_httpx2_failures_are_wrapped_and_not_cached(self, failure):
        requests = 0

        def handle(request):
            nonlocal requests
            requests += 1
            if requests > 1:
                return httpx.Response(200, content=make_project().model_dump_json())
            if isinstance(failure, int):
                return httpx.Response(failure)
            raise failure("temporary failure", request=request)

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handle), base_url="http://dstack/"
        ) as client:
            provider = GatewayProxyAuthProvider(client)
            with pytest.raises(UnexpectedProxyError) as exc:
                await provider.is_project_member("test", "token")
            assert isinstance(exc.value.__cause__, httpx.HTTPError)
            assert await provider.is_project_member("test", "token")
            assert requests == 2

    async def test_no_servers_reaches_auth_error_boundary(self, tmp_path):
        async with HTTPMultiClient(tmp_path) as client:
            provider = GatewayProxyAuthProvider(client)
            with pytest.raises(UnexpectedProxyError) as exc:
                await provider.is_project_member("test", "token")
            assert isinstance(exc.value.__cause__, httpx.RequestError)
            assert exc.value.__cause__.request.url.path == "/api/projects/test/get"

    @pytest.mark.parametrize(
        ("global_role", "is_member", "is_allowed"),
        [
            pytest.param(GlobalRole.USER, True, True, id="member"),
            # The server lets any user into a public project.
            pytest.param(GlobalRole.USER, False, False, id="non-member-of-public-project"),
            pytest.param(GlobalRole.ADMIN, False, True, id="global-admin"),
        ],
    )
    async def test_get_caller_allows_members_and_global_admins(
        self, global_role, is_member, is_allowed
    ):
        user = make_user(global_role)
        project = make_project(members=[user] if is_member else [])

        def handle(request):
            if request.url.path == "/api/projects/test/get":
                return httpx.Response(200, content=project.model_dump_json())
            assert request.url.path == "/api/users/get_my_user"
            assert request.headers["Authorization"] == "Bearer token"
            return httpx.Response(200, content=user.model_dump_json())

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handle), base_url="http://dstack/"
        ) as client:
            caller = await GatewayProxyAuthProvider(client).get_caller("test", "token")
        expected = ProxyCaller(project_id=project.project_id, user_id=user.id)
        assert caller == (expected if is_allowed else None)

    async def test_get_caller_rechecks_global_admin_role(self):
        user = make_user(GlobalRole.ADMIN)
        project = make_project()

        def handle(request):
            if request.url.path == "/api/users/get_my_user":
                return httpx.Response(200, content=user.model_dump_json())
            return httpx.Response(200, content=project.model_dump_json())

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handle), base_url="http://dstack/"
        ) as client:
            provider = GatewayProxyAuthProvider(client)
            assert await provider.get_caller("test", "token") is not None
            user.global_role = GlobalRole.USER
            # The role is cached like access, not for as long as the user ID.
            await _get_cache(GatewayProxyAuthProvider._is_global_admin).clear()
            assert await provider.get_caller("test", "token") is None

    async def test_parses_only_fields_needed_for_access_checks(self):
        # A newer server can return values that this gateway does not know.
        project = make_project().model_dump(mode="json")
        project["members"][0]["project_role"] = "new-role"
        project["new_field"] = "new-value"
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=project)),
            base_url="http://dstack/",
        ) as client:
            assert await GatewayProxyAuthProvider(client).is_project_member("test", "token")

    async def test_get_caller_denies_if_server_denies(self):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(403)),
            base_url="http://dstack/",
        ) as client:
            assert await GatewayProxyAuthProvider(client).get_caller("test", "token") is None

    async def test_get_caller_raises_not_found_if_project_does_not_exist(self):
        requests = 0

        def handle(request):
            nonlocal requests
            requests += 1
            return httpx.Response(404)

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handle), base_url="http://dstack/"
        ) as client:
            provider = GatewayProxyAuthProvider(client)
            for _ in range(2):
                with pytest.raises(ProxyError) as exc:
                    await provider.get_caller("missing", "token")
                assert exc.value.status_code == 404
            assert requests == 1

    async def test_quotes_project_name_in_server_request(self):
        paths = []

        def handle(request):
            paths.append(request.url.raw_path)
            return httpx.Response(404)

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handle), base_url="http://dstack/"
        ) as client:
            with pytest.raises(ProxyError):
                await GatewayProxyAuthProvider(client).get_caller("list?", "token")
        assert paths == [b"/api/projects/list%3F/get"]

    async def test_get_caller_requests_user_once_per_token(self):
        user = make_user()
        project = make_project(members=[user])
        paths = []

        def handle(request):
            paths.append(request.url.path)
            if request.url.path == "/api/users/get_my_user":
                return httpx.Response(200, content=user.model_dump_json())
            return httpx.Response(200, content=project.model_dump_json())

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handle), base_url="http://dstack/"
        ) as client:
            provider = GatewayProxyAuthProvider(client)
            for project_name in ("first", "second", "first"):
                assert await provider.get_caller(project_name, "token") is not None
        assert sorted(paths) == [
            "/api/projects/first/get",
            "/api/projects/second/get",
            "/api/users/get_my_user",
        ]


def _get_auth_cache() -> BaseCache:
    return _get_cache(GatewayProxyAuthProvider._get_project_access)


def _get_cache(cached_method) -> BaseCache:
    # `aiocache.cached` sets `cache` on the wrapper at runtime, but its type doesn't declare it
    return cached_method.cache
