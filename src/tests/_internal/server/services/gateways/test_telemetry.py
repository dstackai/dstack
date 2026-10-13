import logging
import uuid
from typing import Optional

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.gateways import GatewayConfiguration, GatewayOTelConfig
from dstack._internal.proxy.gateway.models import OTelSettings
from dstack._internal.server import settings
from dstack._internal.server.models import (
    BackendModel,
    GatewayModel,
    GatewayReplicaModel,
    ProjectModel,
)
from dstack._internal.server.services.gateways.telemetry import (
    _InvalidOTelConfigError,
    _resolve_otel_config,
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

    @pytest.mark.parametrize(
        ("endpoint", "headers"),
        [
            pytest.param(
                "https://otlp", {"Authorization": "${{ secrets.deleted }}"}, id="missing"
            ),
            pytest.param("${{ secrets.value }}", {}, id="invalid-endpoint"),
            pytest.param(
                "https://otlp", {"Authorization": "${{ secrets.value }}"}, id="invalid-header"
            ),
        ],
    )
    def test_none_if_secrets_unusable(
        self, caplog: pytest.LogCaptureFixture, endpoint: str, headers: dict[str, str]
    ):
        gateway_model, replica_model = _make_models()
        otel = GatewayOTelConfig(endpoint=endpoint, headers=headers, traces=True)

        with caplog.at_level(logging.WARNING):
            otel_settings = get_gateway_replica_otel_settings(
                gateway_model,
                _make_configuration(otel),
                replica_model,
                secrets={"value": "s3cret\n"},
            )

        assert otel_settings is None
        assert "Cannot enable OpenTelemetry" in caplog.text
        assert "s3cret" not in caplog.text


class TestResolveOTelConfig:
    @pytest.mark.parametrize(
        "endpoint",
        ["https://otlp.example.com:4318", "http://10.0.0.1/otlp"],
    )
    def test_accepts_valid_endpoints(self, endpoint: str):
        assert _resolve_otel_config(GatewayOTelConfig(endpoint=endpoint), {}) == (endpoint, {})

    @pytest.mark.parametrize(
        "endpoint",
        [
            "otlp.example.com",
            "ftp://otlp.example.com",
            "https://",
            "https://otlp.example.com:99999",
            "https://otlp.example.com\n",
            " https://otlp.example.com",
        ],
    )
    def test_rejects_invalid_endpoints(self, endpoint: str):
        with pytest.raises(_InvalidOTelConfigError, match="endpoint"):
            _resolve_otel_config(GatewayOTelConfig(endpoint=endpoint), {})

    @pytest.mark.parametrize(
        ("name", "value"),
        [
            pytest.param("Authorization", "Bearer a\nb", id="line-break"),
            pytest.param("Authorization", " Bearer a", id="leading-whitespace"),
            pytest.param("Authorization", "Bearer a ", id="trailing-whitespace"),
            pytest.param("Authorization", "Bearer \u2192", id="non-latin-1"),
            pytest.param("Bad Name", "a", id="invalid-name"),
        ],
    )
    def test_rejects_invalid_headers_without_revealing_values(self, name: str, value: str):
        otel = GatewayOTelConfig(endpoint="https://otlp", headers={name: value})
        with pytest.raises(_InvalidOTelConfigError) as exc_info:
            _resolve_otel_config(otel, {})
        assert "Bearer" not in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestValidateGatewayOTelConfig:
    @pytest.mark.parametrize(
        ("endpoint", "error"),
        [
            pytest.param("${{ secrets.missing }}", "secrets.missing", id="missing"),
            pytest.param("${{ secrets.token }}", "endpoint must be", id="invalid"),
        ],
    )
    async def test_rejects_without_revealing_values(
        self, test_db, session: AsyncSession, endpoint: str, error: str
    ):
        project = await create_project(session=session)
        await create_secret(session=session, project=project, name="token", value="s3cret")
        otel = GatewayOTelConfig(endpoint=endpoint, headers={"A": "${{ secrets.token }}"})

        with pytest.raises(ServerClientError, match=error) as exc_info:
            await validate_gateway_otel_config(session, project, _make_configuration(otel))

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
