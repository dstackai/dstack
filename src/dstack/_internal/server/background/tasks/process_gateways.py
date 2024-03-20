import asyncio

from dstack._internal.core.errors import SSHError
from dstack._internal.server.services.gateways import GatewayConnection, gateway_connections_pool
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def process_gateways():
    # TODO(egor-s): distribute the load evenly
    connections = await gateway_connections_pool.all()
    await asyncio.gather(*(_process_connection(conn) for conn in connections))


async def _process_connection(conn: GatewayConnection):
    try:
        await conn.check_or_restart()
        await conn.try_collect_stats()
    except SSHError as e:
        logger.error("Connection to gateway %s failed: %s", conn.ip_address, e)
