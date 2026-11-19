from typing import Generator
from unittest.mock import patch

import pytest

from dstack._internal.proxy.gateway.testing.common import Mocks


@pytest.fixture
def system_mocks() -> Generator[Mocks, None, None]:
    nginx = "dstack._internal.proxy.gateway.services.nginx"
    connection = "dstack._internal.proxy.lib.services.service_connection"
    with (
        patch(f"{nginx}.sudo") as sudo,
        patch(f"{nginx}.Nginx.reload") as reload_nginx,
        patch(f"{nginx}.Nginx.run_certbot") as run_certbot,
        patch(f"{connection}.ServiceConnection.open") as open_conn,
        patch(f"{connection}.ServiceConnection.close") as close_conn,
        patch(f"{connection}._wait_until_idle") as wait_until_idle,
    ):
        sudo.return_value = []
        # Drains finish right away unless a test holds them
        wait_until_idle.return_value = True
        yield Mocks(
            reload_nginx=reload_nginx,
            run_certbot=run_certbot,
            open_conn=open_conn,
            close_conn=close_conn,
            wait_until_idle=wait_until_idle,
        )
