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
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        try:
            s.bind(("", port))
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except socket.error as e:
            if e.errno == errno.EADDRINUSE:
                return True
            raise
    return False


def allocate_local_ports(jobs: List[Job]) -> Dict[int, int]:
    ports = {}
    for job in jobs:
        ws_logs_port = int(job.env.get("WS_LOGS_PORT"))
        if ws_logs_port:
            ports[ws_logs_port] = ws_logs_port
        for app_spec in job.app_specs or []:
            ports[app_spec.port] = app_spec.port

    # get the closest port to use
    for remote_port in ports:
        if port_in_use(remote_port):
            ports[remote_port] += 1
            while ports[remote_port] in ports or port_in_use(ports[remote_port]):
                ports[remote_port] += 1
    return ports


def make_ssh_tunnel_args(ssh_key: PathLike, hostname: str, ports: Dict[int, int]) -> List[str]:
    args = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-i",
        str(ssh_key),
        f"root@{hostname}",
        "-N",
        "-f",
    ]
    for port_remote, local_port in ports.items():
        args.extend(["-L", f"{local_port}:{hostname}:{port_remote}"])
    return args


def run_ssh_tunnel(ssh_key: PathLike, hostname: str, ports: Dict[int, int]) -> bool:
    args = make_ssh_tunnel_args(ssh_key, hostname, ports)
    return (
        subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    )
