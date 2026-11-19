import uuid
from pathlib import Path

import pytest

from dstack._internal.proxy.gateway.app import lifespan, make_app
from dstack._internal.proxy.gateway.models import ModelEntrypoint
from dstack._internal.proxy.gateway.repo.repo import GatewayProxyRepo
from dstack._internal.proxy.gateway.services.metering import GatewayProxyMeter
from dstack._internal.proxy.gateway.services.nginx import Nginx
from dstack._internal.proxy.gateway.testing.common import Mocks
from dstack._internal.proxy.lib.auth import ProxyCaller
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
async def test_lifespan_writes_metered_tokens_on_shutdown(
    tmp_path: Path, system_mocks: Mocks
) -> None:
    nginx_dir = tmp_path / "nginx"
    (nginx_dir / "sites-enabled").mkdir(parents=True)
    meter = GatewayProxyMeter(tmp_path / "metering")
    app = make_app(repo=GatewayProxyRepo(), nginx=Nginx(nginx_dir=nginx_dir), meter=meter)
    async with lifespan(app):
        meter.add(
            ProxyCaller(project_id=uuid.uuid4(), user_id=uuid.uuid4()),
            make_service("test-proj", "test-run"),
            None,
            input_tokens=9,
            cached_input_tokens=0,
            output_tokens=1,
        )
    assert (tmp_path / "metering" / "1.json").exists()
