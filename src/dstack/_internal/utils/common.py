import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Union

PathLike = Union[str, os.PathLike]


def get_dstack_dir() -> Path:
    return Path.joinpath(Path.home(), ".dstack")


def pretty_date(time: Any = False):
    """
    Get a datetime object or a int() Epoch timestamp and return a
    pretty string like 'an hour ago', 'Yesterday', '3 months ago',
    'just now', etc
    """
    from datetime import datetime

    now = datetime.now()
    if type(time) is int:
        diff = now - datetime.fromtimestamp(time)
    elif isinstance(time, datetime):
        diff = now - time
    elif not time:
        diff = now - now
    second_diff = diff.seconds
    day_diff = diff.days

    if day_diff < 0:
        return ""

    if day_diff == 0:
        if second_diff < 10:
            return "now"
        if second_diff < 60:
            return str(second_diff) + " sec ago"
        if second_diff < 120:
            return "1 min ago"
        if second_diff < 3600:
            return str(round(second_diff / 60)) + " mins ago"
        if second_diff < 7200:
            return "1 hour ago"
        if second_diff < 86400:
            return str(round(second_diff / 3600)) + " hours ago"
    if day_diff == 1:
        return "yesterday"
    if day_diff < 7:
        return str(day_diff) + " days ago"
    if day_diff < 31:
        return str(round(day_diff / 7)) + " weeks ago"
    if day_diff < 365:
        return str(round(day_diff / 30)) + " months ago"
    return str(round(day_diff / 365)) + " years ago"


def since(timestamp: str) -> datetime:
    try:
        seconds = parse_pretty_duration(timestamp)
        return get_current_datetime() - timedelta(seconds=seconds)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(timestamp)
    except ValueError:
        pass
    try:
        return datetime.fromtimestamp(int(timestamp))
    except Exception:
        raise ValueError("Invalid datetime format")


def parse_pretty_duration(duration: str) -> int:
    regex = re.compile(r"(?P<amount>\d+)(?P<unit>s|m|h|d|w)$")
    re_match = regex.match(duration)
    if not re_match:
        raise ValueError(f"Cannot parse the duration {duration}")
    amount, unit = int(re_match.group("amount")), re_match.group("unit")
    multiplier = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 24 * 3600,
        "w": 7 * 24 * 3600,
    }[unit]
    return amount * multiplier


def sizeof_fmt(num, suffix="B"):
    for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, "Yi", suffix)


def removeprefix(s: str, prefix: str) -> str:
    if s.startswith(prefix):
        return s[len(prefix) :]
    return s


def get_current_datetime() -> datetime:
    return datetime.now(tz=timezone.utc)


def get_milliseconds_since_epoch() -> int:
    return int(round(time.time() * 1000))


def timestamps_in_milliseconds_to_datetime(ts: int) -> datetime:
    seconds = ts // 1000
    milliseconds = ts % 1000
    return datetime.fromtimestamp(seconds, tz=timezone.utc).replace(
        microsecond=milliseconds * 1000
    )


def datetime_to_timestamp_in_milliseconds(dt: datetime) -> int:
    milliseconds = dt.microsecond // 1000
    return int(dt.timestamp()) * 1000 + milliseconds
