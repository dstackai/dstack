from typing import Optional
from unittest.mock import Mock

import pytest
from opentelemetry.sdk.trace.sampling import Decision

from dstack._internal.proxy.gateway import otel
from dstack._internal.proxy.gateway.models import OTelSettings


class TestApplySettings:
    @pytest.fixture
    def configure(self, monkeypatch: pytest.MonkeyPatch) -> Mock:
        # Stubbed, as the global providers can only be set once per process
        configure = Mock()
        monkeypatch.setattr(otel, "_configure", configure)
        monkeypatch.setattr(otel, "_applied_settings", None)
        return configure

    def test_does_not_raise_or_retry_if_configuration_fails(self, configure: Mock):
        configure.side_effect = ValueError("bad settings")
        settings = OTelSettings(traces_enabled=True)

        assert otel.apply_settings(settings) is False
        assert otel.apply_settings(settings) is False
        assert otel.apply_settings(OTelSettings(logs_enabled=True)) is True

        configure.assert_called_once_with(settings)

    def test_keeps_disabled_without_settings(self, configure: Mock):
        assert otel.apply_settings(None) is False
        assert otel.apply_settings(OTelSettings()) is False
        configure.assert_not_called()

    def test_applies_first_settings_immediately(self, configure: Mock):
        settings = OTelSettings(traces_enabled=True)

        assert otel.apply_settings(settings) is False
        assert otel.apply_settings(settings) is False

        configure.assert_called_once_with(settings)

    @pytest.mark.parametrize(
        "new_settings",
        [
            pytest.param(OTelSettings(traces_enabled=True, logs_enabled=True), id="changed"),
            pytest.param(None, id="disabled"),
        ],
    )
    def test_requires_restart_to_change_applied_settings(
        self, configure: Mock, new_settings: Optional[OTelSettings]
    ):
        otel.apply_settings(OTelSettings(traces_enabled=True))

        assert otel.apply_settings(new_settings) is True

        configure.assert_called_once()


class TestGetSignalEndpoint:
    @pytest.mark.parametrize(
        ("endpoint", "expected"),
        [
            ("https://otel.example.com:4318", "https://otel.example.com:4318/v1/traces"),
            ("https://example.com/otlp/", "https://example.com/otlp/v1/traces"),
            (None, None),
        ],
    )
    def test_appends_signal_path(self, endpoint: Optional[str], expected: Optional[str]):
        settings = OTelSettings(endpoint=endpoint)
        assert otel._get_signal_endpoint(settings, "traces") == expected


class TestBuildRootSampler:
    def test_samples_auth_subrequests_at_auth_rate(self):
        sampler = otel._build_root_sampler(
            OTelSettings(traces_sample_rate=1.0, traces_auth_sample_rate=0.0)
        )
        registry_result = sampler.should_sample(
            None, trace_id=123, name="POST /api/registry/{project_name}/services/register"
        )
        auth_result = sampler.should_sample(
            None, trace_id=123, name="GET /api/auth/{project_name}"
        )
        assert registry_result.decision == Decision.RECORD_AND_SAMPLE
        assert auth_result.decision == Decision.DROP


class TestGetResource:
    def test_adds_service_to_replica_attributes(self):
        settings = OTelSettings(
            resource_attributes={"service.instance.id": "replica-id", "dstack.gateway.name": "gw"}
        )

        attributes = otel._get_resource(settings).attributes

        assert attributes["service.name"] == "dstack-gateway"
        assert "service.version" in attributes
        assert attributes["service.instance.id"] == "replica-id"
        assert attributes["dstack.gateway.name"] == "gw"
