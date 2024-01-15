import contextlib
from typing import Iterator

from dstack._internal.core.services.ssh.tunnel import RunnerTunnel
from dstack._internal.server.services.gateways.client import GATEWAY_MANAGEMENT_PORT, GatewayClient
from dstack._internal.server.services.jobs import get_runner_ports


@contextlib.contextmanager
def gateway_tunnel_client(hostname: str, id_rsa: str) -> Iterator[GatewayClient]:
    with RunnerTunnel(
        hostname=hostname,
        ssh_port=22,
        user="ubuntu",
        ports=get_runner_ports(ports=[GATEWAY_MANAGEMENT_PORT]),
        id_rsa=id_rsa,
    ) as tun:
        yield GatewayClient(port=tun.ports[GATEWAY_MANAGEMENT_PORT])
