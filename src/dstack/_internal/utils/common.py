import asyncio
import enum
import itertools
import re
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path
from typing import Any, Iterable, List, Optional, TypeVar
from urllib.parse import urlparse

from typing_extensions import ParamSpec

P = ParamSpec("P")
R = TypeVar("R")


async def run_async(func: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
    func_with_args = partial(func, *args, **kwargs)
    return await asyncio.get_running_loop().run_in_executor(None, func_with_args)


def get_dstack_dir() -> Path:
    return Path.joinpath(Path.home(), ".dstack")


def get_current_datetime() -> datetime:
    return datetime.now(tz=timezone.utc)


def get_milliseconds_since_epoch() -> int:
    return int(round(time.time() * 1000))


DateFormatter = Callable[[datetime], str]


def local_time(time: datetime) -> str:
    """Return HH:MM in local timezone"""
    return time.astimezone().strftime("%H:%M")


def pretty_date(time: datetime) -> str:
    """
    Return a pretty string like 'an hour ago', 'Yesterday', '3 months ago', 'just now', etc
    """
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
        weeks = round(diff.days / 7)
        if weeks == 1:
            return str(weeks) + " week ago"
        return str(weeks) + " weeks ago"
    if diff.days < 365:
        months = round(diff.days / 30)
        if months == 1:
            return str(months) + " month ago"
        return str(months) + " months ago"
    years = round(diff.days / 365)
    if years == 1:
        return str(years) + " year ago"
    return str(years) + " years ago"


def pretty_resources(
    *,
    cpu_arch: Optional[Any] = None,
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
        cpu_arch_lower: Optional[str] = None
        if isinstance(cpu_arch, enum.Enum):
            cpu_arch_lower = str(cpu_arch.value).lower()
        elif isinstance(cpu_arch, str):
            cpu_arch_lower = cpu_arch.lower()
        if cpu_arch_lower == "arm":
            cpu_arch_prefix = "arm:"
        else:
            cpu_arch_prefix = ""
        parts.append(f"cpu={cpu_arch_prefix}{cpus}")
    if memory is not None:
        parts.append(f"mem={memory}")
    if disk_size:
        parts.append(f"disk={disk_size}")
    if gpu_count:
        gpu_parts = []
        gpu_parts.append(f"{gpu_name or 'gpu'}")
        if gpu_memory is not None:
            gpu_parts.append(f"{gpu_memory}")
        if gpu_count is not None:
            gpu_parts.append(f"{gpu_count}")
        if total_gpu_memory is not None:
            gpu_parts.append(f"{total_gpu_memory}")
        if compute_capability is not None:
            gpu_parts.append(f"{compute_capability}")

        gpu = ":".join(gpu_parts)
        parts.append(gpu)
    return " ".join(parts)


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


DURATION_UNITS_DESC = [
    ("w", 7 * 24 * 3600),
    ("d", 24 * 3600),
    ("h", 3600),
    ("m", 60),
    ("s", 1),
]


def format_pretty_duration(seconds: int) -> str:
    if seconds == 0:
        return "0s"
    if seconds < 0:
        raise ValueError("Seconds cannot be negative")
    for unit, multiplier in DURATION_UNITS_DESC:
        if seconds % multiplier == 0:
            return f"{seconds // multiplier}{unit}"
    return f"{seconds}s"  # Fallback to seconds if no larger unit fits perfectly


def format_duration_multiunit(seconds: int) -> str:
    """90 -> 1m 30s, 4545 -> 1h 15m 45s, etc"""
    if seconds < 0:
        raise ValueError("Seconds cannot be negative")
    result = ""
    for unit, multiplier in DURATION_UNITS_DESC:
        if unit_value := seconds // multiplier:
            result += f" {unit_value}{unit}"
            seconds -= unit_value * multiplier
    return result.lstrip() or "0s"


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


def get_or_error(v: Optional[T]) -> T:
    """
    Unpacks an optional value. Used to denote that None is not possible in the current context.
    """
    if v is None:
        raise ValueError("Optional value is None")
    return v


def batched(seq: Iterable[T], n: int) -> Iterable[List[T]]:
    it = iter(seq)
    return iter(lambda: list(itertools.islice(it, n)), [])


StrT = TypeVar("StrT", str, bytes)


def concat_url_path(a: StrT, b: StrT) -> StrT:
    if not b:
        return a
    sep = "/" if isinstance(a, str) else b"/"
    return a.removesuffix(sep) + sep + b.removeprefix(sep)


def make_proxy_url(server_url: str, proxy_url: str) -> str:
    """
    Constructs a URL to dstack-proxy services or endpoints.
    `proxy_url` can be a full URL (gateway), in which case it is returned as is,
    or a path (in-server proxy), in which case it is concatenated with `server_url`
    """
    proxy = urlparse(proxy_url)
    if proxy.scheme and proxy.netloc:
        return proxy_url
    server = urlparse(server_url)
    proxy = proxy._replace(
        scheme=server.scheme or "http",
        netloc=server.netloc,
        path=concat_url_path(server.path, proxy.path),
    )
    return proxy.geturl()
