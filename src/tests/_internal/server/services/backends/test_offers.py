import asyncio
import threading
import time
from unittest.mock import Mock

import pytest

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.runs import Requirements
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.testing.common import get_instance_offer_with_availability


class TestGetBackendOffers:
    @pytest.mark.asyncio
    async def test_joins_concurrent_identical_requests(self, monkeypatch: pytest.MonkeyPatch):
        backends_services._INFLIGHT_OFFERS_TASKS.clear()

        backend = Mock()
        backend.TYPE = BackendType.AWS
        requirements = Requirements(resources=ResourcesSpec(cpu=1))
        offer = get_instance_offer_with_availability(backend=BackendType.AWS)

        calls = {"num": 0}
        calls_lock = threading.Lock()

        def _get_offers_tracked(_backend, _requirements):
            with calls_lock:
                calls["num"] += 1
            # Keep one call in flight so concurrent requests can join it.
            time.sleep(0.05)
            return [offer]

        monkeypatch.setattr(backends_services, "get_offers_tracked", _get_offers_tracked)

        async def _fetch():
            offers = await backends_services.get_backend_offers(
                backends=[backend], requirements=requirements
            )
            return list(offers)

        results = await asyncio.gather(*[_fetch() for _ in range(8)])
        assert calls["num"] == 1
        for result in results:
            assert result == [(backend, offer)]
        await asyncio.sleep(0)
        assert backends_services._INFLIGHT_OFFERS_TASKS == {}

    @pytest.mark.asyncio
    async def test_does_not_join_different_requirements(self, monkeypatch: pytest.MonkeyPatch):
        backends_services._INFLIGHT_OFFERS_TASKS.clear()

        backend = Mock()
        backend.TYPE = BackendType.AWS
        offer = get_instance_offer_with_availability(backend=BackendType.AWS)

        calls = {"num": 0}
        calls_lock = threading.Lock()

        def _get_offers_tracked(_backend, _requirements):
            with calls_lock:
                calls["num"] += 1
            time.sleep(0.02)
            return [offer]

        monkeypatch.setattr(backends_services, "get_offers_tracked", _get_offers_tracked)

        requirements1 = Requirements(resources=ResourcesSpec(cpu=1))
        requirements2 = Requirements(resources=ResourcesSpec(cpu=2))

        async def _fetch(requirements):
            offers = await backends_services.get_backend_offers(
                backends=[backend], requirements=requirements
            )
            return list(offers)

        await asyncio.gather(_fetch(requirements1), _fetch(requirements2))
        assert calls["num"] == 2
        await asyncio.sleep(0)
        assert backends_services._INFLIGHT_OFFERS_TASKS == {}

    @pytest.mark.asyncio
    async def test_retries_after_joined_failure(self, monkeypatch: pytest.MonkeyPatch):
        backends_services._INFLIGHT_OFFERS_TASKS.clear()

        backend = Mock()
        backend.TYPE = BackendType.AWS
        requirements = Requirements(resources=ResourcesSpec(cpu=1))
        offer = get_instance_offer_with_availability(backend=BackendType.AWS)

        calls = {"num": 0}
        calls_lock = threading.Lock()

        def _get_offers_tracked(_backend, _requirements):
            with calls_lock:
                calls["num"] += 1
                call_num = calls["num"]
            time.sleep(0.02)
            if call_num == 1:
                raise RuntimeError("boom")
            return [offer]

        monkeypatch.setattr(backends_services, "get_offers_tracked", _get_offers_tracked)

        async def _fetch():
            offers = await backends_services.get_backend_offers(
                backends=[backend], requirements=requirements
            )
            return list(offers)

        first_results = await asyncio.gather(_fetch(), _fetch())
        assert calls["num"] == 1
        assert first_results == [[], []]

        # The failed in-flight task must be cleaned up so the next request can retry.
        await asyncio.sleep(0)
        assert backends_services._INFLIGHT_OFFERS_TASKS == {}

        second_result = await _fetch()
        assert calls["num"] == 2
        assert second_result == [(backend, offer)]
        await asyncio.sleep(0)
        assert backends_services._INFLIGHT_OFFERS_TASKS == {}
