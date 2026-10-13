import signal
from unittest.mock import Mock

import httpx
import pytest

from dstack._internal.proxy.gateway.app import make_app
from dstack._internal.proxy.gateway.models import OTelSettings
from dstack._internal.proxy.gateway.repo.repo import GatewayProxyRepo
from dstack._internal.proxy.gateway.routers import config


def make_client(repo: GatewayProxyRepo) -> httpx.AsyncClient:
    app = make_app(repo)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/")


@pytest.mark.asyncio
class TestUpdateGlobalConfig:
    @pytest.mark.parametrize("restart_required", [False, True])
    async def test_saves_and_applies_otel_settings(
        self, monkeypatch: pytest.MonkeyPatch, restart_required: bool
    ) -> None:
        apply_settings = Mock(return_value=restart_required)
        kill = Mock()
        monkeypatch.setattr(config.otel, "apply_settings", apply_settings)
        monkeypatch.setattr(config.os, "kill", kill)
        repo = GatewayProxyRepo()
        otel_settings = {
            "traces_enabled": True,
            "endpoint": "https://otel.example.com:4318",
            "headers": {"api-key": "secret"},
            "resource_attributes": {"service.instance.id": "replica-id"},
        }

        async with make_client(repo) as client:
            resp = await client.post("/api/config", json={"otel_settings": otel_settings})

        assert resp.status_code == 200
        expected = OTelSettings(**otel_settings)
        assert (await repo.get_config()).otel_settings == expected
        apply_settings.assert_called_once_with(expected)
        if restart_required:
            kill.assert_called_once()
            assert kill.call_args.args[1] == signal.SIGTERM
        else:
            kill.assert_not_called()

    async def test_accepts_config_without_otel_settings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Older servers do not send otel_settings
        apply_settings = Mock(return_value=False)
        monkeypatch.setattr(config.otel, "apply_settings", apply_settings)
        repo = GatewayProxyRepo()

        async with make_client(repo) as client:
            resp = await client.post("/api/config", json={"acme_server": None})

        assert resp.status_code == 200
        assert (await repo.get_config()).otel_settings is None
        apply_settings.assert_called_once_with(None)
