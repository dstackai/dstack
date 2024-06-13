import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, List, Optional, TypeVar, Union


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


def pretty_resources(
    cpus: Optional[Any] = None,
    memory: Optional[Any] = None,
    gpu_count: Optional[Any] = None,
    gpu_name: Optional[Any] = None,
    gpu_memory: Optional[Any] = None,
    total_gpu_memory: Optional[Any] = None,
    compute_capability: Optional[Any] = None,
    disk_size: Optional[Any] = None,
) -> str:
    """
    >>> pretty_resources(cpus=4, memory="16GB")
    '4xCPU, 16GB'
    >>> pretty_resources(cpus=4, memory="16GB", gpu_count=1)
    '4xCPU, 16GB, 1xGPU'
    >>> pretty_resources(cpus=4, memory="16GB", gpu_count=1, gpu_name='A100')
    '4xCPU, 16GB, 1xA100'
    >>> pretty_resources(cpus=4, memory="16GB", gpu_count=1, gpu_name='A100', gpu_memory="40GB")
    '4xCPU, 16GB, 1xA100 (40GB)'
    >>> pretty_resources(cpus=4, memory="16GB", gpu_count=1, total_gpu_memory="80GB")
    '4xCPU, 16GB, 1xGPU (total 80GB)'
    >>> pretty_resources(cpus=4, memory="16GB", gpu_count=2, gpu_name='A100', gpu_memory="40GB", total_gpu_memory="80GB")
    '4xCPU, 16GB, 2xA100 (40GB, total 80GB)'
    >>> pretty_resources(gpu_count=1, compute_capability="8.0")
    '1xGPU (8.0)'
    """
    parts = []
    if cpus is not None:
        parts.append(f"{cpus}xCPU")
    if memory is not None:
        parts.append(f"{memory}")
    if gpu_count:
        gpu_parts = []
        if gpu_memory is not None:
            gpu_parts.append(f"{gpu_memory}")
        if total_gpu_memory is not None:
            gpu_parts.append(f"total {total_gpu_memory}")
        if compute_capability is not None:
            gpu_parts.append(f"{compute_capability}")

        gpu = f"{gpu_count}x{gpu_name or 'GPU'}"
        if gpu_parts:
            gpu += f" ({', '.join(gpu_parts)})"
        parts.append(gpu)
    if disk_size:
        parts.append(f"{disk_size} (disk)")
    return ", ".join(parts)


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


def format_pretty_duration(seconds: int) -> str:
    if seconds < 0:
        raise ValueError("Seconds cannot be negative")
    units = [
        ("w", 7 * 24 * 3600),
        ("d", 24 * 3600),
        ("h", 3600),
        ("m", 60),
        ("s", 1),
    ]
    for unit, multiplier in units:
        if seconds % multiplier == 0:
            return f"{seconds // multiplier}{unit}"
    return f"{seconds}s"  # Fallback to seconds if no larger unit fits perfectly


def sizeof_fmt(num, suffix="B"):
    for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, "Yi", suffix)


def remove_prefix(text: str, prefix: str) -> str:
    if text.startswith(prefix):
        return text[len(prefix) :]
    return text


T = TypeVar("T")


def split_chunks(iterable: Iterable[T], chunk_size: int) -> Iterable[List[T]]:
    """
    Splits an iterable into chunks of at most `chunk_size` items.

    >>> list(split_chunks([1, 2, 3, 4, 5], 2))
    [[1, 2], [3, 4], [5]]
    """

    if chunk_size < 1:
        raise ValueError(f"chunk_size should be a positive integer, not {chunk_size}")

    chunk = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) == chunk_size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


MEMORY_UNITS = {
    "B": 1,
    "K": 2**10,
    "M": 2**20,
    "G": 2**30,
    "T": 2**40,
    "P": 2**50,
}


def parse_memory(memory: str, as_untis: str = "M") -> float:
    """
    Converts memory units to the units specified.
    >>> parse_memory("512Ki", as_units="M")
    0.5
    >>> parse_memory("2Mi", as_units="K")
    2048
    """
    m = re.fullmatch(r"(\d+) *([kmgtp])(i|b)", memory.strip().lower())
    if not m:
        raise ValueError(f"Invalid memory: {memory}")
    value = int(m.group(1))
    units = m.group(2)
    value_in_bytes = value * MEMORY_UNITS[units.upper()]
    result = value_in_bytes / MEMORY_UNITS[as_untis.upper()]
    return result
