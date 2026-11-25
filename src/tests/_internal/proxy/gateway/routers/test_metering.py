import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
import time_machine

from dstack._internal.proxy.gateway.app import make_app
from dstack._internal.proxy.gateway.repo.repo import GatewayProxyRepo
from dstack._internal.proxy.gateway.services.metering import GatewayProxyMeter
from dstack._internal.proxy.lib.auth import ProxyCaller
from dstack._internal.proxy.lib.testing.common import make_service


@pytest.mark.asyncio
async def test_collect_metering(tmp_path: Path):
    caller = ProxyCaller(project_id=uuid.uuid4(), user_id=uuid.uuid4())
    service = make_service("test-proj", "test-run")
    meter = GatewayProxyMeter(tmp_path)
    with time_machine.travel(datetime(2026, 11, 20, 10, 59, tzinfo=timezone.utc), tick=False):
        for input_tokens in (800, 3):
            meter.add(
                caller,
                service,
                None,
                input_tokens=input_tokens,
                cached_input_tokens=0,
                output_tokens=1,
            )
            await meter.flush()
    app = make_app(repo=GatewayProxyRepo(), meter=meter)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/")

    resp = await client.post("/api/metering/collect", json={"after": 1, "limit": 10})

    assert resp.status_code == 200
    assert resp.json() == {
        "batches": [
            {
                "batch_no": 2,
                "created_at": "2026-11-20T10:59:00Z",
                "records": [
                    {
                        "hour": "2026-11-20T10:00:00Z",
                        "project_id": str(caller.project_id),
                        "user_id": str(caller.user_id),
                        "run_id": str(uuid.UUID(service.id)),
                        "export_id": None,
                        "input_tokens": 3,
                        "cached_input_tokens": 0,
                        "output_tokens": 1,
                    }
                ],
            }
        ]
    }
