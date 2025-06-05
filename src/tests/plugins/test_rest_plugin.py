import json
import os
from contextlib import nullcontext as does_not_raise
from unittest import mock
from unittest.mock import Mock

import pytest
import pytest_asyncio
import requests
from pydantic import parse_obj_as
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import ServerClientError, ServerError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.fleets import FleetConfiguration, FleetSpec
from dstack._internal.core.models.gateways import GatewayConfiguration, GatewaySpec
from dstack._internal.core.models.profiles import Profile
from dstack._internal.core.models.resources import Range
from dstack._internal.core.models.runs import RunSpec
from dstack._internal.core.models.volumes import VolumeSpec
from dstack._internal.server.models import ProjectModel
from dstack._internal.server.services import encryption as encryption
from dstack._internal.server.testing.common import (
    create_project,
    create_repo,
    create_user,
    get_fleet_spec,
    get_run_spec,
    get_volume_configuration,
)
from dstack.plugins.builtin.rest_plugin import PLUGIN_SERVICE_URI_ENV_VAR_NAME, CustomApplyPolicy


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
            commands=["echo hello"], port=8000, replicas=parse_obj_as(Range[int], replicas)
        ),
    )
    return spec


async def create_fleet_spec():
    name = "test-fleet-spec"
    fleet_conf = FleetConfiguration(name=name)
    return get_fleet_spec(conf=fleet_conf)


async def create_volume_spec():
    return VolumeSpec(configuration=get_volume_configuration())


async def create_gateway_spec():
    configuration = GatewayConfiguration(
        name="test-gateway-config",
        backend=BackendType.AWS,
        region="us-central",
    )
    return GatewaySpec(configuration=configuration)


@pytest_asyncio.fixture
async def project(session):
    return await create_project(session=session)


@pytest_asyncio.fixture
async def user(session):
    return await create_user(session=session)


@pytest_asyncio.fixture
async def spec(request, session, project):
    if request.param == "run_spec":
        return await create_run_spec(session, project)
    elif request.param == "fleet_spec":
        return await create_fleet_spec()
    elif request.param == "volume_spec":
        return await create_volume_spec()
    elif request.param == "gateway_spec":
        return await create_gateway_spec()
    else:
        raise ValueError(f"Unknown spec fixture: {request.param}")


class TestRESTPlugin:
    @pytest.mark.asyncio
    async def test_on_run_apply_plugin_service_uri_not_set(self):
        with pytest.raises(ServerError):
            CustomApplyPolicy()

    @pytest.mark.asyncio
    @mock.patch.dict(os.environ, {PLUGIN_SERVICE_URI_ENV_VAR_NAME: "http://mock"})
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @pytest.mark.parametrize(
        "spec", ["run_spec", "fleet_spec", "volume_spec", "gateway_spec"], indirect=True
    )
    async def test_on_apply_plugin_service_returns_mutated_spec(
        self, test_db, user, project, spec
    ):
        policy = CustomApplyPolicy()
        mock_response = Mock()
        response_dict = {"spec": spec.dict(), "error": None}

        if isinstance(spec, (RunSpec, FleetSpec)):
            response_dict["spec"]["profile"]["tags"] = {"env": "test", "team": "qa"}
        else:
            response_dict["spec"]["configuration_path"] = "/path/to/something"

        mock_response.text = json.dumps(response_dict)
        mock_response.raise_for_status = Mock()
        with mock.patch("requests.post", return_value=mock_response):
            result = policy.on_apply(user=user.name, project=project.name, spec=spec)
            assert result == type(spec)(**response_dict["spec"])

    @pytest.mark.asyncio
    @mock.patch.dict(os.environ, {PLUGIN_SERVICE_URI_ENV_VAR_NAME: "http://mock"})
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @pytest.mark.parametrize(
        "spec", ["run_spec", "fleet_spec", "volume_spec", "gateway_spec"], indirect=True
    )
    async def test_on_apply_plugin_service_call_fails(self, test_db, user, project, spec):
        policy = CustomApplyPolicy()
        with mock.patch("requests.post", side_effect=requests.RequestException("fail")):
            with pytest.raises(ServerClientError):
                policy.on_apply(user=user.name, project=project.name, spec=spec)

    @pytest.mark.asyncio
    @mock.patch.dict(os.environ, {PLUGIN_SERVICE_URI_ENV_VAR_NAME: "http://mock"})
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @pytest.mark.parametrize(
        "spec", ["run_spec", "fleet_spec", "volume_spec", "gateway_spec"], indirect=True
    )
    async def test_on_apply_plugin_service_connection_fails(self, test_db, user, project, spec):
        policy = CustomApplyPolicy()
        with mock.patch(
            "requests.post", side_effect=requests.ConnectionError("Failed to connect")
        ):
            with pytest.raises(ServerClientError):
                policy.on_apply(user=user.name, project=project.name, spec=spec)

    @pytest.mark.asyncio
    @mock.patch.dict(os.environ, {PLUGIN_SERVICE_URI_ENV_VAR_NAME: "http://mock"})
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @pytest.mark.parametrize(
        "spec", ["run_spec", "fleet_spec", "volume_spec", "gateway_spec"], indirect=True
    )
    async def test_on_apply_plugin_service_returns_invalid_spec(
        self, test_db, user, project, spec
    ):
        policy = CustomApplyPolicy()
        mock_response = Mock()
        mock_response.text = json.dumps({"invalid-key": "abc"})
        mock_response.raise_for_status = Mock()
        with mock.patch("requests.post", return_value=mock_response):
            with pytest.raises(ServerClientError):
                policy.on_apply(user.name, project=project.name, spec=spec)

    @pytest.mark.asyncio
    @mock.patch.dict(os.environ, {PLUGIN_SERVICE_URI_ENV_VAR_NAME: "http://mock"})
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @pytest.mark.parametrize(
        "spec", ["run_spec", "fleet_spec", "volume_spec", "gateway_spec"], indirect=True
    )
    @pytest.mark.parametrize(
        ("error", "expectation"),
        [
            pytest.param(None, does_not_raise(), id="error_none"),
            pytest.param(
                "",
                pytest.raises(
                    ServerClientError, match="Plugin service returned an invalid response"
                ),
                id="error_empty_str",
            ),
            pytest.param(
                "validation failed",
                pytest.raises(
                    ServerClientError, match="Apply request rejected: validation failed"
                ),
                id="error_non_empty_str",
            ),
        ],
    )
    async def test_on_apply_plugin_service_error_handling(
        self, test_db, user, project, spec, error, expectation
    ):
        policy = CustomApplyPolicy()
        mock_response = Mock()
        response_dict = {"spec": spec.dict(), "error": error}
        mock_response.text = json.dumps(response_dict)
        mock_response.raise_for_status = Mock()
        with mock.patch("requests.post", return_value=mock_response):
            with expectation:
                result = policy.on_apply(user=user.name, project=project.name, spec=spec)
                assert result == type(spec)(**response_dict["spec"])
