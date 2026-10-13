import logging
import uuid
from typing import Optional
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.compatibility.gateways import get_gateway_spec_excludes
from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.gateways import (
    GatewayConfiguration,
    GatewayOTelConfig,
    GatewaySpec,
)
from dstack._internal.proxy.gateway.models import OTelSettings
from dstack._internal.server import settings
from dstack._internal.server.models import (
    BackendModel,
    GatewayModel,
    GatewayReplicaModel,
    ProjectModel,
)
from dstack._internal.server.services.gateways import update_gateway_replica_otel_settings
from dstack._internal.server.services.gateways.telemetry import (
    get_gateway_replica_otel_settings,
    validate_gateway_otel_config,
)
from dstack._internal.server.testing.common import (
    create_project,
    create_secret,
    create_user,
)


class TestGetGatewayReplicaOTelSettings:
    @pytest.mark.parametrize(
        "otel",
        [
            pytest.param(None, id="no-otel"),
            pytest.param(GatewayOTelConfig(endpoint="https://otlp"), id="no-signals"),
        ],
    )
    def test_none_if_disabled(self, otel: Optional[GatewayOTelConfig]):
        gateway_model, replica_model = _make_models()

        assert (
            get_gateway_replica_otel_settings(
                gateway_model, _make_configuration(otel), replica_model, secrets={}
            )
            is None
        )

    def test_resolves_secrets_and_identifies_replica(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "SERVER_ENVIRONMENT", "production")
        gateway_model, replica_model = _make_models()
        otel = GatewayOTelConfig(
            endpoint="${{ secrets.otlp_endpoint }}",
            headers={"Authorization": "Bearer ${{ secrets.otlp_token }}", "X-Team": "ml"},
            traces=True,
            metrics=True,
            traces_sample_rate=0.5,
        )

        otel_settings = get_gateway_replica_otel_settings(
            gateway_model,
            _make_configuration(otel),
            replica_model,
            secrets={"otlp_endpoint": "https://otlp.example.com", "otlp_token": "s3cret"},
        )

        assert otel_settings == OTelSettings(
            traces_enabled=True,
            logs_enabled=False,
            metrics_enabled=True,
            endpoint="https://otlp.example.com",
            headers={"Authorization": "Bearer s3cret", "X-Team": "ml"},
            traces_sample_rate=0.5,
            traces_auth_sample_rate=0.01,
            resource_attributes={
                "service.instance.id": str(replica_model.id),
                "dstack.gateway.replica.num": 1,
                "deployment.environment.name": "production",
                "dstack.project.name": "main",
                "dstack.gateway.name": "my-gateway",
                "dstack.backend": "aws",
                "host.name": "203.0.113.5",
                "cloud.region": "us-east-1",
            },
        )

    def test_none_if_secret_missing(self, caplog: pytest.LogCaptureFixture):
        gateway_model, replica_model = _make_models()
        otel = GatewayOTelConfig(
            endpoint="https://otlp",
            headers={"Authorization": "${{ secrets.deleted }}", "X-Key": "${{ secrets.key }}"},
            traces=True,
        )

        with caplog.at_level(logging.WARNING):
            otel_settings = get_gateway_replica_otel_settings(
                gateway_model, _make_configuration(otel), replica_model, secrets={"key": "s3cret"}
            )

        assert otel_settings is None
        assert "secrets.deleted" in caplog.text
        assert "s3cret" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestValidateGatewayOTelConfig:
    async def test_accepts_existing_secrets(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        await create_secret(session=session, project=project, name="token", value="s3cret")
        otel = GatewayOTelConfig(
            endpoint="https://otlp", headers={"Authorization": "Bearer ${{ secrets.token }}"}
        )

        await validate_gateway_otel_config(session, project, _make_configuration(otel))

    async def test_rejects_missing_secrets_without_revealing_values(
        self, test_db, session: AsyncSession
    ):
        project = await create_project(session=session)
        await create_secret(session=session, project=project, name="token", value="s3cret")
        otel = GatewayOTelConfig(
            endpoint="${{ secrets.missing }}",
            headers={"Authorization": "${{ secrets.token }}"},
        )

        with pytest.raises(ServerClientError) as exc_info:
            await validate_gateway_otel_config(session, project, _make_configuration(otel))

        assert "secrets.missing" in str(exc_info.value)
        assert "s3cret" not in str(exc_info.value)

    async def test_does_not_use_other_projects_secrets(self, test_db, session: AsyncSession):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user, name="owner")
        other_project = await create_project(session=session, owner=user, name="other")
        await create_secret(session=session, project=other_project, name="token", value="x")
        otel = GatewayOTelConfig(endpoint="https://otlp", headers={"A": "${{ secrets.token }}"})

        with pytest.raises(ServerClientError):
            await validate_gateway_otel_config(session, project, _make_configuration(otel))


def _make_configuration(otel: Optional[GatewayOTelConfig]) -> GatewayConfiguration:
    return GatewayConfiguration(backend=BackendType.AWS, region="us-east-1", otel=otel)


def _make_models() -> tuple[GatewayModel, GatewayReplicaModel]:
    gateway_model = GatewayModel(
        name="my-gateway",
        project=ProjectModel(name="main"),
        backend=BackendModel(type=BackendType.AWS),
    )
    replica_model = GatewayReplicaModel(
        id=uuid.uuid4(),
        replica_num=1,
        ip_address="203.0.113.5",
        region="us-east-1",
    )
    return gateway_model, replica_model


@pytest.mark.asyncio
class TestUpdateGatewayReplicaOTelSettings:
    async def test_submits_config_only_when_settings_change(self):
        client = Mock()
        client.submit_gateway_config = AsyncMock()
        connection = Mock(ip_address="1.1.1.1", otel_settings=None)
        connection.client = Mock(return_value=_AsyncContext(client))
        otel_settings = OTelSettings(traces_enabled=True, endpoint="https://otlp")

        await update_gateway_replica_otel_settings(connection, None)
        client.submit_gateway_config.assert_not_awaited()

        await update_gateway_replica_otel_settings(connection, otel_settings)
        await update_gateway_replica_otel_settings(connection, otel_settings)
        client.submit_gateway_config.assert_awaited_once_with(otel_settings)
        assert connection.otel_settings == otel_settings

        await update_gateway_replica_otel_settings(connection, None)
        assert client.submit_gateway_config.await_count == 2
        assert connection.otel_settings is None


class _AsyncContext:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *args):
        return None


class TestGatewayConfigurationExcludes:
    def test_excludes_unset_otel_for_older_servers(self):
        configuration = GatewayConfiguration(backend=BackendType.AWS, region="us-east-1")
        excludes = get_gateway_spec_excludes(GatewaySpec(configuration=configuration))
        assert excludes["configuration"]["otel"] is True

    def test_includes_set_otel(self):
        configuration = _make_configuration(GatewayOTelConfig(endpoint="https://otlp"))
        excludes = get_gateway_spec_excludes(GatewaySpec(configuration=configuration))
        assert "otel" not in excludes["configuration"]
