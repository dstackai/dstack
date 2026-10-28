import asyncio
from datetime import timedelta
from unittest.mock import Mock

import pytest

from dstack._internal.server.background.pipeline_tasks.runs import RunFetcher, RunWorker


@pytest.fixture
def fetcher() -> RunFetcher:
    return RunFetcher(
        queue=asyncio.Queue(),
        queue_desired_minsize=1,
        min_processing_interval=timedelta(seconds=5),
        lock_timeout=timedelta(seconds=30),
        heartbeater=Mock(),
    )


@pytest.fixture
def worker() -> RunWorker:
    return RunWorker(queue=Mock(), heartbeater=Mock(), pipeline_hinter=Mock())
