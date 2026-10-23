import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from dstack._internal.proxy.gateway.app import (
    lifespan,
    make_app,
    renew_certificates_periodically,
)
from dstack._internal.proxy.gateway.models import ModelEntrypoint
from dstack._internal.proxy.gateway.repo.repo import GatewayProxyRepo
from dstack._internal.proxy.gateway.services.nginx import Nginx
from dstack._internal.proxy.gateway.testing.common import Mocks
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
async def test_renews_certificates_periodically_despite_errors() -> None:
    nginx = Mock(renew_certificates=AsyncMock(side_effect=[RuntimeError("certbot failed"), None]))
    # The first delay, then one after each of the two renewals; stop at the third
    sleep = AsyncMock(side_effect=[None, None, asyncio.CancelledError()])
    with patch("dstack._internal.proxy.gateway.app.asyncio.sleep", sleep):
        with pytest.raises(asyncio.CancelledError):
            await renew_certificates_periodically(nginx)
    assert nginx.renew_certificates.await_count == 2
