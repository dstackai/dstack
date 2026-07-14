import pytest

from dstack._internal.server.utils.common import (
    is_background_task_name,
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


@pytest.mark.parametrize(
    ["name", "expected"],
    [
        ["pipeline_tasks.VolumeWorker.process", True],
        ["scheduled_tasks.process_metrics", True],
        ["GET /api/project", False],
    ],
)
def test_is_background_task_name(name, expected):
    assert is_background_task_name(name) is expected
