import contextlib
import os
from typing import Iterator

from dstack._internal.server.services.gateways.client import GATEWAY_MANAGEMENT_PORT, GatewayClient
from dstack._internal.server.services.ssh import SSHAutoTunnel


@contextlib.contextmanager
def gateway_tunnel_client(hostname: str, id_rsa: str) -> Iterator[GatewayClient]:
    raise NotImplementedError()  # TODO(egor-s): remove


class GatewayConnection:
    """
    `GatewayConnection` instances persist for the lifetime of the gateway.

    The `GatewayConnection.tunnel` is responsible for establishing a bidirectional tunnel with the gateway.
    The local tunnel is used for the gateway management.
    The reverse tunnel is used for authorizing dstack tokens.
    """

    def __init__(self, ip_address: str, id_rsa: str, server_port: int):
        self.ip_address = ip_address
        args = ["-L", "{temp_dir}/gateway:localhost:%d" % GATEWAY_MANAGEMENT_PORT]
        args += ["-R", f"localhost:8001:localhost:{server_port}"]
        self.tunnel = SSHAutoTunnel(
            f"ubuntu@{ip_address}",
            id_rsa,
            {
                "StrictHostKeyChecking": "no",
                "UserKnownHostsFile": "/dev/null",
                "ExitOnForwardFailure": "yes",
                "StreamLocalBindUnlink": "yes",
                "ConnectTimeout": 1,
                "ServerAliveInterval": 60,
            },
            args,
        )
        self.client = GatewayClient(uds=os.path.join(self.tunnel.temp_dir, "gateway"))
