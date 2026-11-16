import asyncio
import contextvars
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import func, select

from dstack._internal.proxy.lib.schemas.usage import UsageAckResponse, UsageBatchPage
from dstack._internal.server.background.scheduled_tasks import usage
from dstack._internal.server.models import UsageBatchModel, UsageCounterModel
from dstack._internal.server.testing.common import (
    create_backend,
    create_gateway_replica,
    create_project,
    create_user,
)
from tests._internal.server.services.test_usage import batch

DB_SESSION = contextvars.ContextVar("usage_test_db_session", default=False)


class Client:
    def __init__(self, test_db, items):
        self.db = test_db
        self.items = items
        self.acks = []
        self.fetches = 0
        self.lose_ack = False

    def assert_no_db_connection(self):
        # Async sessions are tracked explicitly below, independent of pool implementation.
        assert not DB_SESSION.get()

    async def fetch_usage_batches(self, limit=100):
        self.assert_no_db_connection()
        self.fetches += 1
        return UsageBatchPage(
            collector_id="collector", batches=self.items[:limit], has_more=len(self.items) > limit
        )

    async def acknowledge_usage(self, ids):
        self.assert_no_db_connection()
        async with self.db.get_session() as session:
            committed = set(await session.scalars(select(UsageBatchModel.batch_id)))
            assert set(ids) <= committed
        self.acks.append(ids)
        self.items = [b for b in self.items if b.batch_id not in ids]
        if self.lose_ack:
            self.lose_ack = False
            raise httpx.ReadError("ACK reply lost")
        return UsageAckResponse(acknowledged_batch_ids=ids)


def setup(monkeypatch, db, client):
    original = usage.get_session_ctx

    @asynccontextmanager
    async def tracked():
        token = DB_SESSION.set(True)
        try:
            async with original() as session:
                yield session
        finally:
            DB_SESSION.reset(token)

    monkeypatch.setattr(usage, "get_session_ctx", tracked)

    @asynccontextmanager
    async def connection_client():
        yield client

    connection = type(
        "Connection", (), {"ip_address": "1.1.1.1", "client": staticmethod(connection_client)}
    )()
    monkeypatch.setattr(
        usage.gateway_connections_pool, "all", AsyncMock(return_value=[connection])
    )
    return connection


async def registered(session):
    user = await create_user(session)
    project = await create_project(session, owner=user)
    backend = await create_backend(session, project.id)
    return await create_gateway_replica(session, backend)


@pytest.mark.asyncio
async def test_commit_before_ack_and_lost_reply(session, test_db, monkeypatch):
    await registered(session)
    client = Client(test_db, [batch()])
    setup(monkeypatch, test_db, client)
    client.lose_ack = True
    await usage.collect_gateway_usage()
    # Simulate a retry of the same already committed batch.
    client.items = [batch()]
    await usage.collect_gateway_usage()
    async with test_db.get_session() as s:
        assert await s.scalar(select(func.count()).select_from(UsageCounterModel)) == 1
    assert client.acks == [["batch-1"], ["batch-1"]]


@pytest.mark.asyncio
async def test_failed_transaction_sends_no_ack(session, test_db, monkeypatch):
    await registered(session)
    client = Client(test_db, [batch()])
    setup(monkeypatch, test_db, client)
    original = usage.ingest_usage_batch

    async def fail(*args, **kwargs):
        await original(*args, **kwargs)
        raise RuntimeError("Injected transaction failure")

    monkeypatch.setattr(usage, "ingest_usage_batch", fail)
    await usage.collect_gateway_usage()
    assert not client.acks
    async with test_db.get_session() as s:
        assert await s.scalar(select(func.count()).select_from(UsageBatchModel)) == 0


@pytest.mark.asyncio
async def test_conflict_never_acknowledged(session, test_db, monkeypatch):
    await registered(session)
    client = Client(test_db, [batch()])
    setup(monkeypatch, test_db, client)
    async with test_db.get_session() as s:
        await usage.ingest_usage_batch(s, uuid.uuid4(), "collector", batch())
        await s.commit()
    await usage.collect_gateway_usage()
    assert not client.acks and client.items


@pytest.mark.asyncio
async def test_page_budget_and_overlapping_collectors(session, test_db, monkeypatch):
    await registered(session)
    client = Client(test_db, [batch(f"b-{i}", i) for i in range(5)])
    setup(monkeypatch, test_db, client)
    monkeypatch.setattr(usage, "PAGE_SIZE", 1)
    monkeypatch.setattr(usage, "MAX_PAGES", 2)
    await usage.collect_gateway_usage()
    assert len(client.items) == 3 and client.fetches == 2
    await asyncio.gather(usage.collect_gateway_usage(), usage.collect_gateway_usage())
    await (
        usage.collect_gateway_usage()
    )  # Overlapping pages may replay; a later tick drains the rest.
    async with test_db.get_session() as s:
        assert await s.scalar(select(func.count()).select_from(UsageBatchModel)) == 5


@pytest.mark.asyncio
async def test_old_gateway_skipped_without_stats_calls(session, test_db, monkeypatch):
    await registered(session)
    client = Client(test_db, [])
    setup(monkeypatch, test_db, client)

    async def unavailable(limit=100):
        response = httpx.Response(
            404, request=httpx.Request("GET", "http://gateway/api/usage/batches")
        )
        response.raise_for_status()

    monkeypatch.setattr(client, "fetch_usage_batches", unavailable)
    await usage.collect_gateway_usage()
    assert not client.acks
