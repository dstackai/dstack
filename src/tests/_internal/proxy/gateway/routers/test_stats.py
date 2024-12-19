from collections.abc import Iterable
from unittest.mock import patch

import httpx
import pytest

from dstack._internal.proxy.gateway.app import make_app
from dstack._internal.proxy.gateway.repo.repo import GatewayProxyRepo
from dstack._internal.proxy.lib.models import Service
from dstack._internal.proxy.lib.testing.common import make_project, make_service


def make_client(repo: GatewayProxyRepo) -> httpx.AsyncClient:
    app = make_app(repo)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("services", "collector_stats", "expected_response"),
    [
        pytest.param(
            [
                make_service("test-proj", "srv-1", domain="srv-1.gtw.test"),
                make_service("test-proj", "srv-2", domain="srv-2.gtw.test"),
            ],
            {
                "srv-1.gtw.test": {
                    30: {"requests": 1, "request_time": 0.1},
                    60: {"requests": 2, "request_time": 0.2},
                    300: {"requests": 3, "request_time": 0.3},
                },
                "srv-2.gtw.test": {
                    30: {"requests": 4, "request_time": 0.4},
                    60: {"requests": 5, "request_time": 0.5},
                    300: {"requests": 6, "request_time": 0.6},
                },
            },
            [
                {
                    "project_name": "test-proj",
                    "run_name": "srv-1",
                    "stats": {
                        "30": {"requests": 1, "request_time": 0.1},
                        "60": {"requests": 2, "request_time": 0.2},
                        "300": {"requests": 3, "request_time": 0.3},
                    },
                },
                {
                    "project_name": "test-proj",
                    "run_name": "srv-2",
                    "stats": {
                        "30": {"requests": 4, "request_time": 0.4},
                        "60": {"requests": 5, "request_time": 0.5},
                        "300": {"requests": 6, "request_time": 0.6},
                    },
                },
            ],
            id="collects-two-services",
        ),
        pytest.param(
            [
                make_service("test-proj", "has-stats", domain="has-stats.gtw.test"),
                make_service("test-proj", "no-stats", domain="no-stats.gtw.test"),
            ],
            {
                "has-stats.gtw.test": {
                    30: {"requests": 1, "request_time": 0.1},
                    60: {"requests": 2, "request_time": 0.2},
                    300: {"requests": 3, "request_time": 0.3},
                },
            },
            [
                {
                    "project_name": "test-proj",
                    "run_name": "has-stats",
                    "stats": {
                        "30": {"requests": 1, "request_time": 0.1},
                        "60": {"requests": 2, "request_time": 0.2},
                        "300": {"requests": 3, "request_time": 0.3},
                    },
                },
                {
                    "project_name": "test-proj",
                    "run_name": "no-stats",
                    "stats": {
                        "30": {"requests": 0, "request_time": 0.0},
                        "60": {"requests": 0, "request_time": 0.0},
                        "300": {"requests": 0, "request_time": 0.0},
                    },
                },
            ],
            id="adds-empty-stats-if-no-stats",
        ),
        pytest.param(
            [
                make_service("test-proj", "relevant", domain="relevant.gtw.test"),
            ],
            {
                "relevant.gtw.test": {
                    30: {"requests": 1, "request_time": 0.1},
                    60: {"requests": 2, "request_time": 0.2},
                    300: {"requests": 3, "request_time": 0.3},
                },
                "irrelevant.gtw.test": {
                    30: {"requests": 4, "request_time": 0.4},
                    60: {"requests": 5, "request_time": 0.5},
                    300: {"requests": 6, "request_time": 0.6},
                },
            },
            [
                {
                    "project_name": "test-proj",
                    "run_name": "relevant",
                    "stats": {
                        "30": {"requests": 1, "request_time": 0.1},
                        "60": {"requests": 2, "request_time": 0.2},
                        "300": {"requests": 3, "request_time": 0.3},
                    },
                },
            ],
            id="ignores-irrelevant-hosts",
        ),
        pytest.param(
            [],
            {},
            [],
            id="no-services",
        ),
    ],
)
async def test_collect_stats(services: Iterable[Service], collector_stats, expected_response):
    repo = GatewayProxyRepo()
    for service in services:
        await repo.set_project(make_project(service.project_name))
        await repo.set_service(service)
    client = make_client(repo)
    with patch(
        "dstack._internal.proxy.gateway.services.stats.StatsCollector.collect"
    ) as collect_mock:
        collect_mock.return_value = collector_stats
        resp = await client.get("/api/stats/collect")
        assert resp.status_code == 200
        assert resp.json() == expected_response
