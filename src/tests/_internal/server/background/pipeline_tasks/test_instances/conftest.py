import asyncio
import datetime as dt
from unittest.mock import Mock

import pytest

from dstack._internal.core.backends.base.compute import GoArchType
from dstack._internal.server.background.pipeline_tasks.instances import (
    InstanceFetcher,
    InstanceWorker,
)
from dstack._internal.server.background.pipeline_tasks.instances import (
    ssh_deploy as instances_ssh_deploy,
)
from dstack._internal.server.schemas.instances import InstanceCheck


@pytest.fixture
def fetcher() -> InstanceFetcher:
    return InstanceFetcher(
        queue=asyncio.Queue(),
        queue_desired_minsize=1,
        min_processing_interval=dt.timedelta(seconds=10),
        lock_timeout=dt.timedelta(seconds=30),
        heartbeater=Mock(),
    )


@pytest.fixture
def worker() -> InstanceWorker:
    return InstanceWorker(queue=asyncio.Queue(), heartbeater=Mock())


@pytest.fixture
def host_info() -> dict:
    return {
        "gpu_vendor": "nvidia",
        "gpu_name": "T4",
        "gpu_memory": 16384,
        "gpu_count": 1,
        "addresses": ["192.168.100.100/24"],
        "disk_size": 260976517120,
        "cpus": 32,
        "memory": 33544130560,
    }


@pytest.fixture
def deploy_instance_mock(monkeypatch: pytest.MonkeyPatch, host_info: dict) -> Mock:
    mock = Mock(
        return_value=(
            InstanceCheck(reachable=True),
            host_info,
            GoArchType.AMD64,
        )
    )
    monkeypatch.setattr(instances_ssh_deploy, "_deploy_instance", mock)
    return mock
