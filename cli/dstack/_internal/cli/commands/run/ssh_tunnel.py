import errno
import socket
import subprocess
from typing import Dict, List, Optional

from dstack._internal.configurators.ports import PortUsedError


class PortsLock:
    def __init__(self, restrictions: Optional[Dict[int, int]] = None):
        self.restrictions = restrictions or {}
        self.sockets: Dict[int, socket.socket] = {}

    def acquire(self) -> "PortsLock":
        assert not self.sockets
        assigned_ports = set()

        # mapped by user
        for app_port, local_port in self.restrictions.items():
            if not local_port:  # None or 0
                continue
            if local_port in assigned_ports:
                raise PortUsedError(f"Mapped port {app_port}:{local_port} is already in use")
            sock = self._listen(local_port)
            if sock is None:
                raise PortUsedError(f"Mapped port {app_port}:{local_port} is already in use")
            self.sockets[app_port] = sock
            assigned_ports.add(local_port)

        # mapped automatically
        for app_port, local_port in self.restrictions.items():
            if local_port:
                continue
            local_port = app_port
            while True:
                if local_port not in assigned_ports:
                    sock = self._listen(local_port)
                    if sock is not None:
                        break
                local_port += 1
            self.sockets[app_port] = sock
            assigned_ports.add(local_port)
        return self

    def release(self) -> Dict[int, int]:
        mapping = self.dict()
        for sock in self.sockets.values():
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.close()
        self.sockets = {}
        return mapping

    def dict(self) -> Dict[int, int]:
        return {app_port: sock.getsockname()[1] for app_port, sock in self.sockets.items()}

    @staticmethod
    def _listen(port: int) -> Optional[socket.socket]:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("", port))
            return sock
        except socket.error as e:
            if e.errno == errno.EADDRINUSE:
                return None
            raise


def make_ssh_tunnel_args(run_name: str, ports: Dict[int, int]) -> List[str]:
    args = [
        "ssh",
        run_name,
        "-N",
        "-f",
    ]
    for port_remote, local_port in ports.items():
        args.extend(["-L", f"{local_port}:localhost:{port_remote}"])
    return args


def run_ssh_tunnel(run_name: str, ports: Dict[int, int]) -> bool:
    args = make_ssh_tunnel_args(run_name, ports)
    return (
        subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    )
