import json
from datetime import datetime
from pathlib import Path

import pytest

from dstack._internal.proxy.gateway.app import lifespan, make_app
from dstack._internal.proxy.gateway.models import ModelEntrypoint
from dstack._internal.proxy.gateway.repo.repo import GatewayProxyRepo
from dstack._internal.proxy.gateway.services.nginx import Nginx
from dstack._internal.proxy.gateway.testing.common import Mocks
from dstack._internal.proxy.lib.models import (
    ChatModel,
    OpenAIChatModelFormat,
    TGIChatModelFormat,
)
from dstack._internal.proxy.lib.testing.common import make_project, make_service


@pytest.mark.asyncio
async def test_lifespan(tmp_path: Path, system_mocks: Mocks) -> None:
    repo = GatewayProxyRepo()
    await repo.set_project(make_project("test-proj"))
    await repo.set_entrypoint(
        ModelEntrypoint(project_name="proj-1", domain="gateway.gtw.test", https=True)
    )
    await repo.set_service(
        make_service("test-proj", "test-run", domain="test-run.gtw.test", https=True)
    )
    nginx_dir = tmp_path / "nginx"
    conf_dir = nginx_dir / "sites-enabled"
    conf_dir.mkdir(parents=True)
    app = make_app(repo=repo, nginx=Nginx(nginx_dir=nginx_dir))
    async with lifespan(app):
        assert (conf_dir / "00-log-format.conf").exists()
        assert (conf_dir / "443-gateway.gtw.test.conf").exists()
        assert (conf_dir / "443-test-run.gtw.test.conf").exists()
        assert (nginx_dir / "nginx.conf").exists()
        assert system_mocks.open_conn.call_count == 1
        assert system_mocks.close_conn.call_count == 0
    assert system_mocks.close_conn.call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("model_format", ["openai", "tgi"])
async def test_lifespan_migrates_proxy_buffering(
    tmp_path: Path, system_mocks: Mocks, model_format: str
) -> None:
    state_file = tmp_path / "state-v2.json"
    repo = GatewayProxyRepo(file=state_file)
    for project in ("model-proj", "web-proj"):
        await repo.set_project(make_project(project))
        await repo.set_service(
            make_service(project, "same-run", domain=f"{project}.gtw.test", https=False)
        )
    await repo.set_model(
        ChatModel(
            project_name="model-proj",
            name="test-model",
            created_at=datetime(2026, 1, 1),
            run_name="same-run",
            format_spec=(
                OpenAIChatModelFormat(prefix="/v1")
                if model_format == "openai"
                else TGIChatModelFormat(chat_template="{{ messages }}", eos_token="</s>")
            ),
        )
    )
    # Old gateways saved services without a proxy_buffering field.
    state = json.loads(state_file.read_text())
    for services in state["services"].values():
        for service in services.values():
            service.pop("proxy_buffering", None)
    state_file.write_text(json.dumps(state))
    nginx_dir = tmp_path / "nginx"
    conf_dir = nginx_dir / "sites-enabled"
    conf_dir.mkdir(parents=True)
    # Restart twice to cover both migration and subsequent persisted-state recovery.
    for _ in range(2):
        repo = GatewayProxyRepo.load(state_file)
        app = make_app(repo=repo, nginx=Nginx(nginx_dir=nginx_dir))
        async with lifespan(app):
            model_conf = (conf_dir / "443-model-proj.gtw.test.conf").read_text()
            web_conf = (conf_dir / "443-web-proj.gtw.test.conf").read_text()
            assert "proxy_buffering off;" in model_conf
            assert "proxy_buffering off;" not in web_conf
            persisted = json.loads(state_file.read_text())
            assert persisted["services"]["model-proj"]["same-run"]["proxy_buffering"] is False
            assert persisted["services"]["web-proj"]["same-run"]["proxy_buffering"] is True
