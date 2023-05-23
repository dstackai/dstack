import errno
import socket
import subprocess
from contextlib import closing
from typing import Dict, List

from dstack.core.job import Job
from dstack.providers.ports import PortUsedError
from dstack.utils.common import PathLike


def get_free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


def port_in_use(port: int) -> bool:
    try:
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            s.bind(("", port))
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except socket.error as e:
        if e.errno == errno.EADDRINUSE:
            return True
        raise
    return False


def allocate_local_ports(jobs: List[Job]) -> Dict[int, int]:
    ports = {}
    for job in jobs[:1]:  # todo multiple jobs
        if "WS_LOGS_PORT" in job.env:
            ports[int(job.env["WS_LOGS_PORT"])] = None
        for app_spec in job.app_specs or []:
            ports[app_spec.port] = app_spec.map_to_port

    map_to_ports = set()
    # mapped by user
    for port, map_to_port in ports.items():
        if not map_to_port:  # None or 0
            continue
        if map_to_port in map_to_ports or port_in_use(map_to_port):
            raise PortUsedError(f"Mapped port {port}:{map_to_port} is already in use")
        map_to_ports.add(map_to_port)
    # mapped automatically
    for port, map_to_port in ports.items():
        if map_to_port:
            continue
        map_to_port = port
        while map_to_port in map_to_ports or port_in_use(map_to_port):
            map_to_port += 1
        ports[port] = map_to_port
        map_to_ports.add(map_to_port)
    return ports


def make_ssh_tunnel_args(
    ssh_key: PathLike, hostname: str, ports: Dict[int, int], backend_type: str
) -> List[str]:
    username = "root"
    if backend_type == "azure":
        # root login is disabled on azure
        # TODO: use non-root for all backends
        username = "ubuntu"
    args = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-i",
        str(ssh_key),
        f"{username}@{hostname}",
        "-N",
        "-f",
    ]
    for port_remote, local_port in ports.items():
        args.extend(["-L", f"{local_port}:localhost:{port_remote}"])
    return args


def run_ssh_tunnel(
    ssh_key: PathLike, hostname: str, ports: Dict[int, int], backend_type: str
) -> bool:
    args = make_ssh_tunnel_args(ssh_key, hostname, ports, backend_type)
    return (
        subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    )
