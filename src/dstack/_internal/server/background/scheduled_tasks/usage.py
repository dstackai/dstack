"""Fetch durable minute batches, commit receipts, then ACK over existing SSH connections."""

import asyncio
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager

import httpx
from sqlalchemy import select

from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import GatewayReplicaModel
from dstack._internal.server.services.gateways.connection import GatewayConnection
from dstack._internal.server.services.gateways.pool import gateway_connections_pool
from dstack._internal.server.services.usage import ingest_usage_batch
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)
PAGE_SIZE = 100
MAX_PAGES = 10
COLLECTION_TIMEOUT = 12
_sqlite_ingestion_lock = asyncio.Lock()


async def collect_gateway_usage() -> None:
    async with get_session_ctx() as session:
        rows = (
            await session.execute(
                select(GatewayReplicaModel.id, GatewayReplicaModel.ip_address).where(
                    GatewayReplicaModel.active == True
                )
            )
        ).all()
    identities: dict[str, list[uuid.UUID]] = defaultdict(list)
    for replica_id, address in rows:
        if address is not None:
            identities[address].append(replica_id)
    semaphore = asyncio.Semaphore(8)

    async def collect(connection: GatewayConnection) -> None:
        candidates = identities.get(connection.ip_address, [])
        if len(candidates) != 1:
            # Ambiguous/recycled addresses cannot establish a verified billing source.
            return
        async with semaphore:
            try:
                async with asyncio.timeout(COLLECTION_TIMEOUT):
                    await _collect_connection(connection, candidates[0])
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in (404, 405):
                    logger.warning(
                        "Usage collection HTTP failure from %s: %s", connection.ip_address, exc
                    )
            except Exception:
                logger.exception(
                    "Usage collection failed from %s; unacknowledged batches retained",
                    connection.ip_address,
                )

    await asyncio.gather(
        *(collect(connection) for connection in await gateway_connections_pool.all())
    )


async def _collect_connection(connection: GatewayConnection, replica_id: uuid.UUID) -> None:
    for _ in range(MAX_PAGES):
        async with connection.client() as client:
            page = await client.fetch_usage_batches(PAGE_SIZE)
        if not page.batches:
            return
        # SQLite is single-server; lock before opening a session. PG relies on DB constraints.
        async with _ingestion_lock():
            async with get_session_ctx() as session:
                for batch in page.batches:
                    await ingest_usage_batch(session, replica_id, page.collector_id, batch)
            # get_session_ctx commits and closes before leaving this block.
        ids = [batch.batch_id for batch in page.batches]
        async with connection.client() as client:
            await client.acknowledge_usage(ids)
        if not page.has_more:
            return


@asynccontextmanager
async def _ingestion_lock():
    if get_db().dialect_name == "sqlite":
        async with _sqlite_ingestion_lock:
            yield
    else:
        yield
