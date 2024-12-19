"""Gateway-related constants useful in various dstack modules."""

from pathlib import Path

DSTACK_DIR_ON_GATEWAY = Path("/home/ubuntu/dstack")
SERVER_CONNECTIONS_DIR_ON_GATEWAY = DSTACK_DIR_ON_GATEWAY / "server-connections"
PROXY_PORT_ON_GATEWAY = 8000
