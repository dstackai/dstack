from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent

import pytest
from freezegun import freeze_time

from dstack._internal.proxy.gateway.schemas.stats import Stat
from dstack._internal.proxy.gateway.services.stats import StatsCollector


@pytest.mark.asyncio
@freeze_time(datetime(2024, 12, 6, 12, 10, tzinfo=timezone.utc))
@pytest.mark.parametrize(
    ("access_log", "expected_result"),
    [
        pytest.param(
            dedent(
                """
                2024-12-06T12:08:00+00:00 srv-0.gtw.test 200 0.100 1
                2024-12-06T12:08:00+00:00 srv-1.gtw.test 200 1.100 1
                2024-12-06T12:09:15+00:00 srv-0.gtw.test 200 0.200 1
                2024-12-06T12:09:15+00:00 srv-1.gtw.test 200 1.200 1
                2024-12-06T12:09:45+00:00 srv-0.gtw.test 200 0.300 1
                """
            ),
            {
                "srv-0.gtw.test": {
                    30: Stat(requests=1, request_time=0.3),
                    60: Stat(requests=2, request_time=0.25),
                    300: Stat(requests=3, request_time=0.2),
                },
                "srv-1.gtw.test": {
                    30: Stat(requests=0, request_time=0.0),
                    60: Stat(requests=1, request_time=1.2),
                    300: Stat(requests=2, request_time=1.15),
                },
            },
            id="multiple-services",
        ),
        pytest.param(
            dedent(
                """
                2024-12-06T12:08:00+00:00 srv.gtw.test 200 0.100 1
                2024-12-06T12:08:00+00:00 srv.gtw.test 200 0.200 1
                2024-12-06T12:08:00+00:00 srv.gtw.test 200 0.300 1
                2024-12-06T12:08:01+00:00 srv.gtw.test 200 0.400 1
                2024-12-06T12:08:01+00:00 srv.gtw.test 200 0.500 1
                """
            ),
            {
                "srv.gtw.test": {
                    30: Stat(requests=0, request_time=0.0),
                    60: Stat(requests=0, request_time=0.0),
                    300: Stat(requests=5, request_time=0.3),
                },
            },
            id="multiple-entries-per-second",
        ),
        pytest.param(
            dedent(
                """
                2024-12-06T12:04:50+00:00 srv.gtw.test 200 0.400 1
                2024-12-06T12:08:00+00:00 srv.gtw.test 200 0.300 1
                2024-12-06T12:09:15+00:00 srv.gtw.test 200 0.200 1
                2024-12-06T12:09:45+00:00 srv.gtw.test 200 0.100 1
                """
            ),
            {
                "srv.gtw.test": {
                    30: Stat(requests=1, request_time=0.1),
                    60: Stat(requests=2, request_time=0.15),
                    300: Stat(requests=3, request_time=0.2),
                },
            },
            id="ignores-out-of-window",
        ),
        pytest.param(
            dedent(
                """
                2024-12-06T12:08:01+00:00 srv.gtw.test 200 0.100 1
                2024-12-06T12:08:02+00:00 srv.gtw.test 200 0.200 0
                2024-12-06T12:08:03+00:00 srv.gtw.test 200 0.300 1
                """
            ),
            {
                "srv.gtw.test": {
                    30: Stat(requests=0, request_time=0.0),
                    60: Stat(requests=0, request_time=0.0),
                    300: Stat(requests=2, request_time=0.2),
                },
            },
            id="ignores-replica-not-hit",
        ),
        pytest.param(
            dedent(
                """
                2024-12-06T12:08:01+00:00 srv.gtw.test 200 0.100
                2024-12-06T12:08:02+00:00 srv.gtw.test 303 0.200
                2024-12-06T12:08:03+00:00 srv.gtw.test 401 0.300
                2024-12-06T12:08:04+00:00 srv.gtw.test 502 0.400
                2024-12-06T12:08:05+00:00 srv.gtw.test 403 0.500
                2024-12-06T12:08:06+00:00 srv.gtw.test 404 0.600
                """
            ),
            {
                "srv.gtw.test": {
                    30: Stat(requests=0, request_time=0.0),
                    60: Stat(requests=0, request_time=0.0),
                    300: Stat(requests=4, request_time=0.25),
                },
            },
            id="ignores-irrelevant-statuses-in-legacy-pre-0.19.11-log",
        ),
        pytest.param(
            "",
            {},
            id="empty-log",
        ),
    ],
)
async def test_collect_stats(access_log: str, expected_result: dict, tmp_path: Path) -> None:
    access_log_path = tmp_path / "dstack.access.log"
    access_log_path.write_text(access_log.lstrip())
    collector = StatsCollector(access_log_path)
    result = await collector.collect()
    assert result == expected_result


@pytest.mark.asyncio
@freeze_time(datetime(2024, 12, 6, 12, 10, tzinfo=timezone.utc))
async def test_collect_stats_after_log_update(tmp_path: Path) -> None:
    access_log_path = tmp_path / "dstack.access.log"
    collector = StatsCollector(access_log_path)
    first_chunk = dedent(
        """
        2024-12-06T12:09:15+00:00 srv.gtw.test 200 0.100
        2024-12-06T12:09:20+00:00 srv.gtw.test 200 0.200
        """
    ).lstrip()
    second_chunk = dedent(
        """
        2024-12-06T12:09:40+00:00 srv.gtw.test 200 0.300
        2024-12-06T12:09:45+00:00 srv.gtw.test 200 0.400
        2024-12-06T12:09:50+00:00 srv.gtw.test 200 0.500
        """
    ).lstrip()
    first_chunk_stats = {
        "srv.gtw.test": {
            30: Stat(requests=0, request_time=0.0),
            60: Stat(requests=2, request_time=0.15),
            300: Stat(requests=2, request_time=0.15),
        },
    }
    both_chunks_stats = {
        "srv.gtw.test": {
            30: Stat(requests=3, request_time=0.4),
            60: Stat(requests=5, request_time=0.3),
            300: Stat(requests=5, request_time=0.3),
        },
    }
    with open(access_log_path, "w") as f:
        f.write(first_chunk)
        f.flush()
        result = await collector.collect()
        assert result == first_chunk_stats
        f.write(second_chunk)
        f.flush()
        result = await collector.collect()
        assert result == both_chunks_stats
