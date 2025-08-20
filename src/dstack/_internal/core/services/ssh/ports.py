import errno
import socket
from typing import Dict, List, Optional

from dstack._internal.compat import IS_WINDOWS
from dstack._internal.core.errors import DstackError
from dstack._internal.core.models.configurations import PortMapping

RESERVED_PORTS_START = 10000
RESERVED_PORTS_END = 10999


class PortUsedError(DstackError):
    pass


class PortsLock:
    def __init__(self, restrictions: Optional[Dict[int, int]] = None):
        self.restrictions = restrictions or {}
        self.sockets: Dict[int, socket.socket] = {}

    def acquire(self) -> "PortsLock":
        assert not self.sockets
        assigned_ports = set()

        # mapped by user
        for remote_port, local_port in self.restrictions.items():
            if not local_port:  # None or 0
                continue
            if local_port in assigned_ports:
                raise PortUsedError(f"Port {local_port} is already in use")
            sock = self._listen(local_port)
            if sock is None:
                raise PortUsedError(f"Port {local_port} is already in use")
            self.sockets[remote_port] = sock
            assigned_ports.add(local_port)

        # mapped automatically
        for remote_port, local_port in self.restrictions.items():
            if local_port:
                continue
            local_port = remote_port
            while True:
                if local_port not in assigned_ports:
                    sock = self._listen(local_port)
                    if sock is not None:
                        break
                local_port += 1
            self.sockets[remote_port] = sock
            assigned_ports.add(local_port)
        return self

    def release(self) -> Dict[int, int]:
        mapping = self.dict()
        for sock in self.sockets.values():
            sock.close()
        self.sockets = {}
        return mapping

    def dict(self) -> Dict[int, int]:
        d = {}
        for remote_port, local_port in self.restrictions.items():
            if local_port:
                d[remote_port] = local_port
            else:
                d[remote_port] = self.sockets[remote_port].getsockname()[1]
        return d

    def __str__(self) -> str:
        return f"<PortsLock: {self.dict()}>"

    @staticmethod
    def _listen(port: int) -> Optional[socket.socket]:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if IS_WINDOWS:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)  # type: ignore[attr-defined]
            sock.bind(("", port))
            return sock
        except socket.error as e:
            if e.errno == errno.EADDRINUSE:
                return None
            raise


def filter_reserved_ports(ports: List[PortMapping]) -> List[PortMapping]:
    return [
        pm for pm in ports if not (RESERVED_PORTS_START <= pm.container_port <= RESERVED_PORTS_END)
    ]
