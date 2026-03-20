from typing import Optional
from urllib.parse import urlsplit


def parse_hostname_port(address: str) -> tuple[str, Optional[int]]:
    err_msg = "must be valid HOSTNAME[:PORT]"
    if "//" in address:
        raise ValueError(err_msg)
    res = urlsplit(f"//{address}")
    if any((res.path, res.query, res.fragment, res.username, res.password)):
        raise ValueError(err_msg)
    hostname = res.hostname
    if not hostname:
        raise ValueError(err_msg)
    try:
        port = res.port
    except ValueError as e:
        raise ValueError(err_msg) from e
    return hostname, port
