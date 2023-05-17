from typing import Iterable, Optional

from dstack.core.error import DstackError

RESERVED_PORTS_START = 2000
RESERVED_PORTS_END = 2999


class PortReservedError(DstackError):
    pass


class PortUsedError(DstackError):
    pass


class PortsRegistry:
    def __init__(self, reserved: Optional[Iterable[int]] = None):
        if reserved is None:
            reserved = range(RESERVED_PORTS_START, RESERVED_PORTS_END + 1)
        self.reserved = set(reserved)
        self.used = set()

    def allocate(self, port: int) -> int:
        if port in self.reserved:
            raise PortReservedError(f"Can't allocate reserved port {port}")
        if port is self.used:
            raise PortUsedError(f"Port {port} is already in use")
        return port
