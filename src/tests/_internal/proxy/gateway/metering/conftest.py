import pytest
import pytest_asyncio

from tests._internal.proxy.gateway.metering.harness import Harness


@pytest_asyncio.fixture
async def harness(tmp_path):
    # A real process covers HTTP cancellation, shutdown, and durable restart boundaries.
    instance = Harness(tmp_path)
    await instance.start()
    try:
        yield instance
    finally:
        await instance.stop()


def pytest_addoption(parser):
    parser.addoption("--run-metering-realtime", action="store_true", default=False)


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-metering-realtime", default=False):
        for item in items:
            if "metering_realtime" in item.keywords:
                item.add_marker(pytest.mark.skip(reason="requires --run-metering-realtime"))
