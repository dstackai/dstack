from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import pytest
from freezegun import freeze_time

from dstack._internal.utils.common import (
    batched,
    concat_url_path,
    format_duration_multiunit,
    has_duplicates,
    local_time,
    make_proxy_url,
    parse_memory,
    pretty_date,
    sizeof_fmt,
)


@pytest.mark.parametrize(
    ("dt", "result"),
    [
        (datetime.fromisoformat("1970-01-01T12:34"), "12:34"),
        (datetime.fromisoformat("2024-12-01T01:02:03"), "01:02"),
    ],
)
def test_local_time(dt: datetime, result: str) -> None:
    assert local_time(dt) == result


@freeze_time(datetime(2023, 10, 4, 12, 0, tzinfo=timezone.utc))
class TestPrettyDate:
    def test_now(self):
        now = datetime.now(tz=timezone.utc)
        assert pretty_date(now) == "now"

    def test_seconds_ago(self):
        now = datetime.now(tz=timezone.utc)
        past_time = now - timedelta(seconds=30)
        assert pretty_date(past_time) == "30 sec ago"

    def test_one_minute_ago(self):
        now = datetime.now(tz=timezone.utc)
        past_time = now - timedelta(minutes=1)
        assert pretty_date(past_time) == "1 min ago"

    def test_minutes_ago(self):
        now = datetime.now(tz=timezone.utc)
        past_time = now - timedelta(minutes=45)
        assert pretty_date(past_time) == "45 mins ago"

    def test_one_hour_ago(self):
        now = datetime.now(tz=timezone.utc)
        past_time = now - timedelta(hours=1)
        assert pretty_date(past_time) == "1 hour ago"

    def test_hours_ago(self):
        now = datetime.now(tz=timezone.utc)
        past_time = now - timedelta(hours=5)
        assert pretty_date(past_time) == "5 hours ago"

    def test_yesterday(self):
        now = datetime.now(tz=timezone.utc)
        yesterday = now - timedelta(days=1)
        assert pretty_date(yesterday) == "yesterday"

    def test_days_ago(self):
        now = datetime.now(tz=timezone.utc)
        past_time = now - timedelta(days=5)
        assert pretty_date(past_time) == "5 days ago"

    def test_week_ago(self):
        now = datetime.now(tz=timezone.utc)
        past_time = now - timedelta(days=7)
        assert pretty_date(past_time) == "1 week ago"

    def test_weeks_ago(self):
        now = datetime.now(tz=timezone.utc)
        past_time = now - timedelta(days=21)
        assert pretty_date(past_time) == "3 weeks ago"

    def test_month_ago(self):
        now = datetime.now(tz=timezone.utc)
        past_time = now - timedelta(days=31)
        assert pretty_date(past_time) == "1 month ago"

    def test_months_ago(self):
        now = datetime.now(tz=timezone.utc)
        past_time = now - timedelta(days=90)
        assert pretty_date(past_time) == "3 months ago"

    def test_year_ago(self):
        now = datetime.now(tz=timezone.utc)
        past_time = now - timedelta(days=400)
        assert pretty_date(past_time) == "1 year ago"

    def test_years_ago(self):
        now = datetime.now(tz=timezone.utc)
        past_time = now - timedelta(days=700)
        assert pretty_date(past_time) == "2 years ago"

    def test_future_time(self):
        now = datetime.now(tz=timezone.utc)
        future_time = now + timedelta(hours=1)
        assert pretty_date(future_time) == ""


class TestFormatDurationMultiunit:
    @pytest.mark.parametrize(
        ("input", "output"),
        [
            (0, "0s"),
            (59, "59s"),
            (60, "1m"),
            (61, "1m 1s"),
            (694861, "1w 1d 1h 1m 1s"),
            (86401, "1d 1s"),
        ],
    )
    def test(self, input: int, output: str) -> None:
        assert format_duration_multiunit(input) == output

    def test_forbids_negative(self) -> None:
        with pytest.raises(ValueError):
            format_duration_multiunit(-1)


@pytest.mark.parametrize(
    "iterable, expected",
    [
        ([1, 2, 3, 4], False),
        ([1, 2, 3, 4, 2], True),
        (iter([1, 2, 3, 4]), False),
        (iter([1, 2, 3, 4, 2]), True),
        ("abcde", False),
        ("hello", True),
        ([1, "a"], False),
        ([1, "a", 1], True),
        ([[1, 2], [3, 4]], False),
        ([[1, 2], [1, 2]], True),
        ([{"a": "b"}, {"a": "c"}], False),
        ([{"a": "b"}, {"a": "b"}], True),
        ([{}, {}], True),
        ([], False),
        ([1], False),
    ],
)
def test_has_duplicates(iterable, expected):
    assert has_duplicates(iterable) == expected


class TestParseMemory:
    @pytest.mark.parametrize(
        "memory,as_units,expected",
        [
            ("1024Ki", "M", 1),
            ("512Ki", "M", 0.5),
            ("2Gi", "M", 2048),
            ("1024Ki", "K", 1024),
        ],
    )
    def test_parses_memory(self, memory, as_units, expected):
        assert parse_memory(memory, as_untis=as_units) == expected


class TestBatched:
    @pytest.mark.parametrize(
        ("iterable", "n", "expected_batches"),
        [
            ([1, 2, 3, 4], 2, [[1, 2], [3, 4]]),
            ([1, 2, 3], 2, [[1, 2], [3]]),
            ([1, 2], 2, [[1, 2]]),
            ([1], 2, [[1]]),
            ([], 2, []),
            ({"a": 1, "b": 2, "c": 3}, 2, [["a", "b"], ["c"]]),
            ((x for x in range(5)), 3, [[0, 1, 2], [3, 4]]),
        ],
    )
    def test_batched(
        self, iterable: Iterable[Any], n: int, expected_batches: list[list[Any]]
    ) -> None:
        assert list(batched(iterable, n)) == expected_batches

    @pytest.mark.parametrize("n", [0, -1])
    def test_raises_on_invalid_n(self, n: int) -> None:
        with pytest.raises(ValueError):
            list(batched([1, 2, 3], n))


@pytest.mark.parametrize(
    ("a", "b", "result"),
    [
        ("/a/b", "c/d", "/a/b/c/d"),
        ("/a/b/", "/c/d", "/a/b/c/d"),
        ("/a/b//", "//c/d", "/a/b///c/d"),
        ("/a", "", "/a"),
        ("/a", "/", "/a/"),
        ("", "a", "/a"),
        ("/", "a", "/a"),
        ("", "", ""),
    ],
)
def test_concat_url_path(a: str, b: str, result: str) -> None:
    assert concat_url_path(a, b) == result
    assert concat_url_path(a.encode(), b.encode()) == result.encode()


@pytest.mark.parametrize(
    ("server_url", "proxy_url", "expected_url"),
    [
        pytest.param(
            "http://localhost:3000",
            "https://gateway.mycompany.example/",
            "https://gateway.mycompany.example/",
        ),
        (
            "https://dstack.mycompany.example/",
            "http://gateway.mycompany.example/some/path",
            "http://gateway.mycompany.example/some/path",
        ),
        (
            "http://localhost:3000",
            "/proxy/services/main/service/",
            "http://localhost:3000/proxy/services/main/service/",
        ),
        (
            "http://localhost:3000/",
            "/proxy/models/main",
            "http://localhost:3000/proxy/models/main",
        ),
        (
            "https://dstack.mycompany.example/some/prefix",
            "/proxy/models/main",
            "https://dstack.mycompany.example/some/prefix/proxy/models/main",
        ),
    ],
)
def test_make_proxy_url(server_url, proxy_url, expected_url):
    assert make_proxy_url(server_url, proxy_url) == expected_url


class TestSizeofFmt:
    @pytest.mark.parametrize(
        ("num", "suffix", "expected"),
        [
            (0, "B", "0.0B"),
            (1023, "B", "1023.0B"),
            (1024, "B", "1.0KiB"),
            (1536, "B", "1.5KiB"),
            (1048576, "B", "1.0MiB"),
            (1073741824, "B", "1.0GiB"),
            (1099511627776, "B", "1.0TiB"),
            (1125899906842624, "B", "1.0PiB"),
            (1152921504606846976, "B", "1.0EiB"),
            (1180591620717411303424, "B", "1.0ZiB"),
            (1208925819614629174706176, "B", "1.0YiB"),
            (2000, "", "2.0Ki"),
            (3000000, "Hz", "2.9MiHz"),
        ],
    )
    def test_sizeof_fmt(self, num: int, suffix: str, expected: str) -> None:
        assert sizeof_fmt(num, suffix) == expected
