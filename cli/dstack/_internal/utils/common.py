import copy
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Union

PathLike = Union[str, os.PathLike]


def get_dstack_dir() -> Path:
    return Path.joinpath(Path.home(), ".dstack")


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


def since(timestamp: str) -> datetime:
    regex = re.compile(r"(?P<amount>\d+)(?P<unit>s|m|h|d|w)$")
    re_match = regex.match(timestamp)
    if re_match:
        datetime_value = _relative_timestamp_to_datetime(
            int(re_match.group("amount")), re_match.group("unit")
        )
        return datetime_value
    try:
        return datetime.fromisoformat(timestamp)
    except ValueError:
        pass
    try:
        return datetime.fromtimestamp(int(timestamp))
    except Exception:
        raise ValueError("Invalid datetime format")


def _relative_timestamp_to_datetime(amount, unit):
    multiplier = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 24 * 3600,
        "w": 7 * 24 * 3600,
    }[unit]
    return get_current_datetime() + timedelta(seconds=amount * multiplier * -1)


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


def format_list(items: Optional[list], *, formatter=str) -> Optional[str]:
    if items is None:
        return None
    return "[{}]".format(", ".join(formatter(item) for item in items))


def merge_workflow_data(
    data: Dict[str, Any], override: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    override = override or {}
    result = {}
    for key in data.keys() | override.keys():
        if key not in override:
            result[key] = copy.deepcopy(data[key])
        elif key not in data:
            result[key] = copy.deepcopy(override[key])
        else:
            a, b = data[key], override[key]
            if isinstance(a, dict) and isinstance(b, dict):
                result[key] = merge_workflow_data(a, b)
            else:
                result[key] = copy.deepcopy(b)
    return result
