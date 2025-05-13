from dstack._internal.core.errors import ServerError
from dstack._internal.server.models import ProjectModel, UserModel
from plugins.rest_plugin.src.rest_plugin import PreApplyPolicy, PLUGIN_SERVICE_URI_ENV_VAR_NAME
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import parse_obj_as
import os
import json
import requests
from unittest.mock import Mock

from dstack._internal.core.models.runs import RunSpec
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.profiles import Profile
from dstack._internal.core.models.resources import Range
from dstack._internal.server.testing.common import (
    create_project,
    create_user,
    create_repo,
    get_run_spec,
)
from dstack._internal.server.testing.conf import session, test_db  # noqa: F401
from dstack._internal.server.services import encryption as encryption  # import for side-effect
import pytest_asyncio
from unittest import mock


async def create_run_spec(
    session: AsyncSession,
    project: ProjectModel,
    replicas: str = 1,
) -> RunSpec:
    repo = await create_repo(session=session, project_id=project.id)
    run_name = "test-run"
    profile = Profile(name="test-profile")
    spec = get_run_spec(
        repo_id=repo.name,
        run_name=run_name,
        profile=profile,
        configuration=ServiceConfiguration(
            commands=["echo hello"],
            port=8000,
            replicas=parse_obj_as(Range[int], replicas)
        ),
    )
    return spec

@pytest_asyncio.fixture
async def project(session):
    return await create_project(session=session)

@pytest_asyncio.fixture
async def user(session):
    return await create_user(session=session)

@pytest_asyncio.fixture
async def run_spec(session, project):
    return await create_run_spec(session=session, project=project)


class TestRESTPlugin:
    @pytest.mark.asyncio
    async def test_on_run_apply_plugin_service_uri_not_set(self):
        with pytest.raises(ServerError):
            policy = PreApplyPolicy()

    @pytest.mark.asyncio
    @mock.patch.dict(os.environ, {PLUGIN_SERVICE_URI_ENV_VAR_NAME: "http://mock"})
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_on_run_apply_plugin_service_returns_mutated_spec(self, test_db, user, project, run_spec):
        policy = PreApplyPolicy()
        mock_response = Mock()
        run_spec_dict = run_spec.dict()
        run_spec_dict["profile"]["tags"] = {"env": "test", "team": "qa"}
        mock_response.text = json.dumps(run_spec_dict)
        mock_response.raise_for_status = Mock()
        with mock.patch("requests.post", return_value=mock_response):
            result = policy.on_apply(user=user.name, project=project.name, spec=run_spec)
            assert result == RunSpec(**run_spec_dict)

    @pytest.mark.asyncio
    @mock.patch.dict(os.environ, {PLUGIN_SERVICE_URI_ENV_VAR_NAME: "http://mock"})
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_on_run_apply_plugin_service_call_fails(self, test_db, user, project, run_spec):
        policy = PreApplyPolicy()
        with mock.patch("requests.post", side_effect=requests.RequestException("fail")):
            result = policy.on_apply(user=user.name, project=project.name, spec=run_spec)
            assert result == run_spec

    @pytest.mark.asyncio
    @mock.patch.dict(os.environ, {PLUGIN_SERVICE_URI_ENV_VAR_NAME: "http://mock"})
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_on_run_apply_plugin_service_returns_invalid_spec(self, test_db, user, project, run_spec):
        policy = PreApplyPolicy()
        mock_response = Mock()
        mock_response.text = json.dumps({"invalid-key": "abc"})
        mock_response.raise_for_status = Mock()
        with mock.patch("requests.post", return_value=mock_response):
            result = policy.on_apply(user.name, project=project.name, spec=run_spec)
            # return original run spec
            assert result == run_spec
        