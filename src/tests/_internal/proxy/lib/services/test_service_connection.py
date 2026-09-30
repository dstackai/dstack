from unittest.mock import Mock

import pytest

from dstack._internal.proxy.lib.models import Service
from dstack._internal.proxy.lib.services.service_connection import get_service_replica_client
from dstack._internal.proxy.lib.testing.common import make_service


@pytest.mark.asyncio
class TestGetServiceReplicaClient:
    async def test_gateway_client_uses_service_read_timeout(self) -> None:
        service = make_service("test-proj", "test-run", domain="test-run.gtw.test")
        service = Service(**{**service.model_dump(), "read_timeout": 900})
        client = await get_service_replica_client(service, repo=Mock(), service_conn_pool=Mock())
        assert client.timeout.read == 900
