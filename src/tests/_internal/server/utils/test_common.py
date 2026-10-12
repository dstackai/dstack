import asyncio
import inspect

import pytest

from dstack._internal.server.utils.common import (
    gather_async,
    gather_map_async,
    join_byte_stream_checked,
)


@pytest.mark.parametrize(
    ["stream", "max_size", "result"],
    [
        [[b"12", b"34", b"56"], 7, b"123456"],
        [[b"12", b"34", b"56"], 6, b"123456"],
        [[b"12", b"34", b"56"], 5, None],
        [[b"12", b"34", b"56"], 0, None],
        [[], 0, b""],
    ],
)
def test_join_byte_stream_checked(stream, max_size, result):
    assert join_byte_stream_checked(iter(stream), max_size) == result


@pytest.mark.parametrize(
    ["stream", "max_size"],
    [
        [[b"12", b"34", b"56"], 5],
        [[b"12", b"34", b"56"], 0],
    ],
)
def test_join_byte_stream_checked_stops_iteration_when_limit_reached(stream, max_size):
    def generator(stream):
        for chunk in stream:
            yield chunk
        raise RuntimeError("Stream end reached, but next value was requested")

    assert join_byte_stream_checked(generator(stream), max_size) is None


class TestGatherMapAsync:
    @pytest.mark.asyncio
    async def test_returns_items_with_results_in_order(self):
        async def double(x: int) -> int:
            return x * 2

        assert await gather_map_async([3, 1, 2], double) == [(3, 6), (1, 2), (2, 4)]

    @pytest.mark.asyncio
    async def test_returns_exceptions(self):
        error = ValueError("odd")

        async def even_only(x: int) -> int:
            if x % 2:
                raise error
            return x

        result = await gather_map_async([1, 2], even_only, return_exceptions=True)
        assert result == [(1, error), (2, 2)]

    @pytest.mark.asyncio
    async def test_limits_concurrency(self):
        tracker = _ConcurrencyTracker()
        items = list(range(5))
        result = await gather_map_async(items, tracker.call, max_concurrency=2)
        assert result == [(x, x) for x in items]
        assert tracker.peak == 2


class TestGatherAsync:
    @pytest.mark.asyncio
    async def test_returns_results_in_order(self):
        async def add(x: int, *, y: int) -> int:
            return x + y

        assert await gather_async([add(1, y=2), add(3, y=4)]) == [3, 7]

    @pytest.mark.asyncio
    async def test_returns_exceptions(self):
        error = ValueError("odd")

        async def even_only(x: int) -> int:
            if x % 2:
                raise error
            return x

        result = await gather_async([even_only(1), even_only(2)], return_exceptions=True)
        assert result == [error, 2]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ["max_concurrency", "expected_peak"],
        [
            [None, 5],
            [1, 1],
            [2, 2],
            [10, 5],
        ],
    )
    async def test_limits_concurrency(self, max_concurrency, expected_peak):
        tracker = _ConcurrencyTracker()
        result = await gather_async(
            [tracker.call(x) for x in range(5)], max_concurrency=max_concurrency
        )
        assert result == list(range(5))
        assert tracker.peak == expected_peak

    @pytest.mark.asyncio
    @pytest.mark.parametrize("max_concurrency", [None, 1, 2])
    async def test_cancels_remaining_calls_on_error(self, max_concurrency):
        tracker = _ConcurrencyTracker()
        coros = [
            tracker.call(0, fail=True),
            tracker.call(1, block=True),
            tracker.call(2, block=True),
        ]
        with pytest.raises(ValueError, match="0"):
            await gather_async(coros, max_concurrency=max_concurrency)
        assert tracker.running == 0
        assert all(inspect.getcoroutinestate(c) == inspect.CORO_CLOSED for c in coros)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("max_concurrency", [0, -1])
    async def test_rejects_max_concurrency_below_one(self, max_concurrency):
        tracker = _ConcurrencyTracker()
        coro = tracker.call(1)
        with pytest.raises(ValueError, match="max_concurrency"):
            await gather_async([coro], max_concurrency=max_concurrency)
        assert inspect.getcoroutinestate(coro) == inspect.CORO_CLOSED


class _ConcurrencyTracker:
    def __init__(self) -> None:
        self.running = 0
        self.peak = 0

    async def call(self, x: int, *, fail: bool = False, block: bool = False) -> int:
        self.running += 1
        self.peak = max(self.peak, self.running)
        try:
            # Yield to the event loop so other calls can start if the limit allows
            for _ in range(3):
                await asyncio.sleep(0)
            if fail:
                raise ValueError(x)
            if block:
                # Never set, only cancellation ends the call
                await asyncio.Event().wait()
            return x
        finally:
            self.running -= 1
