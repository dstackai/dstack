import subprocess
from pathlib import Path
from typing import Dict, List, Union

from dstack.core.job import Job


def allocate_local_ports(jobs: List[Job]) -> Dict[int, int]:
    ports = {}
    for job in jobs:  # todo: allocate local ports
        ws_logs_port = job.env.get("WS_LOGS_PORT")
        if ws_logs_port:
            ports[ws_logs_port] = ws_logs_port
        for app_spec in job.app_specs:
            port = job.ports[app_spec.port_index]
            ports[port] = port
    return ports


def make_ssh_tunnel_args(
    ssh_key: Path, hostname: str, ports: Dict[int, int]
) -> List[Union[str, Path]]:
    args = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-i",
        ssh_key,
        f"root@{hostname}",
        "-N",
        "-f",
    ]
    for port_remote, local_port in ports.items():
        args.extend(["-L", f"{local_port}:{hostname}:{port_remote}"])
    return args


def run_ssh_tunnel(ssh_key: Path, hostname: str, ports: Dict[int, int]):
    args = make_ssh_tunnel_args(ssh_key, hostname, ports)
    subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
