import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Union


def get_dstack_dir() -> Path:
    return Path.joinpath(Path.home(), ".dstack")


def get_current_datetime() -> datetime:
    return datetime.now(tz=timezone.utc)


def get_milliseconds_since_epoch() -> int:
    return int(round(time.time() * 1000))


def pretty_date(time: Union[datetime, int] = False) -> str:
    """
    Get a datetime object or an epoch timestamp and return a
    pretty string like 'an hour ago', 'Yesterday', '3 months ago',
    'just now', etc
    """
    if isinstance(time, int):
        time = datetime.fromtimestamp(time, tz=timezone.utc)
    now = get_current_datetime()
    diff = now - time
    if diff.days < 0:
        return ""

    if diff.days == 0:
        if diff.seconds < 10:
            return "now"
        if diff.seconds < 60:
            return str(diff.seconds) + " sec ago"
        if diff.seconds < 120:
            return "1 min ago"
        if diff.seconds < 3600:
            return str(round(diff.seconds / 60)) + " mins ago"
        if diff.seconds < 7200:
            return "1 hour ago"
        if diff.seconds < 86400:
            return str(round(diff.seconds / 3600)) + " hours ago"
    if diff.days == 1:
        return "yesterday"
    if diff.days < 7:
        return str(diff.days) + " days ago"
    if diff.days < 31:
        return str(round(diff.days / 7)) + " weeks ago"
    if diff.days < 365:
        return str(round(diff.days / 30)) + " months ago"
    years = round(diff.days / 365)
    if years == 1:
        return str(years) + " year ago"
    return str(years) + " years ago"


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
