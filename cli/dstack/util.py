from typing import Optional, Any
from datetime import datetime, timedelta
import re

from botocore.utils import parse_timestamp, datetime2timestamp


def _quoted(s: Optional[str]) -> str:
    if s:
        return f'"{s}"'
    else:
        return "None"


def _quoted_masked(s: Optional[str]) -> str:
    if s:
        return f"\"{'*' * len(s)}\""
    else:
        return "None"


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


def since(timestamp):
    regex = re.compile(r"(?P<amount>\d+)(?P<unit>s|m|h|d|w)$")
    re_match = regex.match(timestamp)
    if re_match:
        datetime_value = _relative_timestamp_to_datetime(
            int(re_match.group("amount")), re_match.group("unit")
        )
    else:
        datetime_value = parse_timestamp(timestamp)
    return int(datetime2timestamp(datetime_value) * 1000)


def _relative_timestamp_to_datetime(amount, unit):
    multiplier = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 24 * 3600,
        "w": 7 * 24 * 3600,
    }[unit]
    return datetime.utcnow() + timedelta(seconds=amount * multiplier * -1)
