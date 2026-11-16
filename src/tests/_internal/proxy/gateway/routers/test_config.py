import asyncio
from datetime import datetime, timezone

import httpx
import pytest

from dstack._internal.proxy.gateway.app import make_app
from dstack._internal.proxy.gateway.repo.repo import GatewayProxyRepo
from dstack._internal.proxy.gateway.services.metering_store import MeteringStore
from dstack._internal.proxy.lib.models import ChatModel, OpenAIChatModelFormat
from dstack._internal.proxy.lib.services.usage import VLLM_PROFILE
from dstack._internal.proxy.lib.testing.common import make_service


@pytest.mark.asyncio
async def test_old_config_update_preserves_metering_and_disabled_creates_no_file(tmp_path):
    repo = GatewayProxyRepo()
    path = tmp_path / "usage.json"
    app = make_app(repo=repo, metering_store=MeteringStore(path))
    await repo.set_service(make_service("p", "run", run_id="service"))
    await repo.set_model(
        ChatModel(
            project_name="p",
            name="model",
            run_name="run",
            created_at=datetime.now(timezone.utc),
            format_spec=OpenAIChatModelFormat(format="openai", prefix="/v1"),
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://control"
    ) as client:
        assert (await client.get("/api/usage/batches")).status_code == 404
        assert not path.exists()
        assert (
            await client.post(
                "/api/config", json={"usage_metering_profiles": {"service": VLLM_PROFILE}}
            )
        ).status_code == 200
        assert path.exists()
        assert (await client.post("/api/config", json={"acme_eab_kid": "kid"})).status_code == 200
        config = await repo.get_config()
        assert config.usage_metering_profiles == {"service": VLLM_PROFILE}
        assert config.acme_settings.eab_kid == "kid"
        assert (
            await client.post(
                "/api/config", json={"usage_metering_profiles": {"missing": VLLM_PROFILE}}
            )
        ).status_code == 400
    await app.state.proxy_dependency_injector.get_usage_observer().close()


@pytest.mark.asyncio
async def test_concurrent_legacy_config_cannot_erase_enabled_profiles(tmp_path, monkeypatch):
    repo = GatewayProxyRepo()
    app = make_app(repo=repo, metering_store=MeteringStore(tmp_path / "usage.json"))
    await repo.set_service(make_service("p", "run", run_id="service"))
    await repo.set_model(
        ChatModel(
            project_name="p",
            name="model",
            run_name="run",
            created_at=datetime.now(timezone.utc),
            format_spec=OpenAIChatModelFormat(format="openai", prefix="/v1"),
        )
    )
    entered = asyncio.Event()
    release = asyncio.Event()
    original = repo.set_config

    async def delayed(config):
        if config.usage_metering_profiles and not entered.is_set():
            entered.set()
            await release.wait()
        await original(config)

    monkeypatch.setattr(repo, "set_config", delayed)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://control"
    ) as client:
        enabling = asyncio.create_task(
            client.post("/api/config", json={"usage_metering_profiles": {"service": VLLM_PROFILE}})
        )
        await entered.wait()
        legacy = asyncio.create_task(client.post("/api/config", json={"acme_eab_kid": "new-kid"}))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        release.set()
        assert (await enabling).status_code == 200
        assert (await legacy).status_code == 200
        assert (await repo.get_config()).usage_metering_profiles == {"service": VLLM_PROFILE}
    await app.state.proxy_dependency_injector.get_usage_observer().close()
