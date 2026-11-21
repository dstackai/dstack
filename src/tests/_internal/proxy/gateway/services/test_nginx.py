import asyncio
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from dstack._internal.proxy.gateway.services.nginx import Nginx
from dstack._internal.proxy.lib.errors import UnexpectedProxyError

SUBPROCESS_RUN = "dstack._internal.proxy.gateway.services.nginx.subprocess.run"


class TestRunCertbotRenew:
    def test_renews_and_reloads_nginx_on_deploy(self) -> None:
        with patch(SUBPROCESS_RUN) as run:
            run.return_value = Mock(returncode=0, stderr=b"")
            Nginx.run_certbot_renew()
        cmd = run.call_args.args[0]
        assert cmd[0] == "sudo"
        assert cmd[cmd.index("certbot") + 1] == "renew"
        assert "--non-interactive" in cmd
        assert cmd[cmd.index("--deploy-hook") + 1] == "systemctl reload nginx.service"

    def test_raises_on_failure(self) -> None:
        with patch(SUBPROCESS_RUN) as run:
            run.return_value = Mock(returncode=1, stderr=b"Failed to renew\nexample.com\n")
            with pytest.raises(UnexpectedProxyError, match="Failed to renew example.com"):
                Nginx.run_certbot_renew()


@pytest.mark.asyncio
async def test_renew_certificates_waits_for_registration(tmp_path: Path) -> None:
    nginx = Nginx(nginx_dir=tmp_path)
    with patch.object(Nginx, "run_certbot_renew") as run_certbot_renew:
        async with nginx._lock:  # e.g. a service registration is running certbot
            task = asyncio.create_task(nginx.renew_certificates())
            await asyncio.sleep(0.1)
            run_certbot_renew.assert_not_called()
        await task
        run_certbot_renew.assert_called_once()
