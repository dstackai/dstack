from datetime import datetime, timedelta, timezone

import pytest
from freezegun import freeze_time

from dstack._internal.utils.common import parse_memory, pretty_date


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

    def test_weeks_ago(self):
        now = datetime.now(tz=timezone.utc)
        past_time = now - timedelta(days=21)
        assert pretty_date(past_time) == "3 weeks ago"

    def test_months_ago(self):
        now = datetime.now(tz=timezone.utc)
        past_time = now - timedelta(days=90)
        assert pretty_date(past_time) == "3 months ago"

    def test_years_ago(self):
        now = datetime.now(tz=timezone.utc)
        past_time = now - timedelta(days=400)
        assert pretty_date(past_time) == "1 year ago"

    def test_future_time(self):
        now = datetime.now(tz=timezone.utc)
        future_time = now + timedelta(hours=1)
        assert pretty_date(future_time) == ""

    def test_epoch_timestamp(self):
        epoch_time = 1609459200  # January 1, 2021
        assert pretty_date(epoch_time) == "3 years ago"


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
