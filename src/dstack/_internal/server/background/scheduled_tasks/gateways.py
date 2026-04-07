import asyncio

from sqlalchemy import select

from dstack._internal.core.errors import SSHError
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import (
    GatewayComputeModel,
)
from dstack._internal.server.services.gateways import (
    GatewayConnection,
    gateway_connections_pool,
)
from dstack._internal.server.services.locking import advisory_lock_ctx
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def process_gateways_connections():
    await _remove_inactive_connections()
    await _process_active_connections()


async def _remove_inactive_connections():
    async with get_session_ctx() as session:
        res = await session.execute(
            select(GatewayComputeModel.ip_address).where(GatewayComputeModel.active == True)
        )
    active_connection_ips = set(res.scalars().all())
    for conn in await gateway_connections_pool.all():
        if conn.ip_address not in active_connection_ips:
            await gateway_connections_pool.remove(conn.ip_address)


async def _process_active_connections():
    connections = await gateway_connections_pool.all()
    # Two server processes on a single host cannot process
    # gateway connections and init gateway connections concurrently:
    # Race conditions cause conflicting tunnels being opened.
    async with get_session_ctx() as session:
        async with advisory_lock_ctx(
            bind=session,
            dialect_name=get_db().dialect_name,
            resource="gateway_tunnels",
        ):
            await asyncio.gather(*(_process_connection(conn) for conn in connections))


async def _process_connection(conn: GatewayConnection):
    try:
        await conn.check_or_restart()
    except SSHError as e:
        logger.error("Connection to gateway %s failed: %s", conn.ip_address, e)
        return

    await conn.try_collect_stats()
