import asyncio
import logging
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import timedelta
from unittest.mock import Mock

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError

from dstack._internal.proxy.lib.schemas.usage import (
    UsageAckResponse,
    UsageBatchPage,
    UsageDrainResponse,
)
from dstack._internal.server.db import Database
from dstack._internal.server.models import (
    BackendModel,
    BaseModel,
    GatewayModel,
    GatewayReplicaModel,
    UsageBatchModel,
    UsageCounterModel,
)
from dstack._internal.server.services.gateways import usage
from dstack._internal.server.services.gateways.connection import GatewayConnection
from dstack._internal.server.services.usage import ingest_usage_batch
from dstack._internal.server.testing.common import (
    create_backend,
    create_gateway,
    create_gateway_replica,
    create_project,
    create_user,
)
from dstack._internal.utils.common import get_current_datetime
from tests._internal.server.services.test_usage import batch


class GatewayQueue:
    def __init__(self, ip_address, items):
        self.connection = Mock(spec=GatewayConnection, ip_address=ip_address, client=self.client)
        self.items = items
        self.acks = []
        self.fetches = 0

    @asynccontextmanager
    async def client(self):
        yield self

    async def fetch_usage_batches(self, limit):
        self.fetches += 1
        return UsageBatchPage(batches=self.items[:limit], has_more=len(self.items) > limit)

    async def acknowledge_usage(self, ids):
        self.acks.append(ids)
        self.items = [b for b in self.items if b.batch_id not in ids]
        return UsageAckResponse(acknowledged_batch_ids=ids)

    async def drain_usage(self):
        return UsageDrainResponse(sealed=True, empty=not self.items)


async def claim(session, replica):
    replica.lock_token = uuid.uuid4()
    replica.lock_expires_at = get_current_datetime() + timedelta(seconds=30)
    replica.lock_owner = "GatewayReplicaPipeline"
    await session.commit()


@pytest_asyncio.fixture
async def replica(session):
    user = await create_user(session)
    project = await create_project(session, owner=user)
    backend = await create_backend(session, project.id)
    gateway = await create_gateway(session, project.id, backend.id)
    replica = await create_gateway_replica(session, backend, gateway_id=gateway.id)
    await claim(session, replica)
    return replica


@pytest.mark.asyncio
class TestDrainGatewayUsage:
    @pytest.mark.parametrize("unsupported", [False, True])
    async def test_continues_collecting_closed_minutes_while_drain_is_pending(
        self, session, replica, monkeypatch, unsupported
    ):
        queue = GatewayQueue(replica.ip_address, [batch()])

        async def waiting():
            if unsupported:
                response = httpx.Response(
                    404, request=httpx.Request("POST", "http://gateway/drain")
                )
                response.raise_for_status()
            return UsageDrainResponse(sealed=False, empty=False)

        monkeypatch.setattr(queue, "drain_usage", waiting)
        assert not await usage.drain_gateway_usage(
            queue.connection, replica.id, replica.gateway_id, replica.lock_token
        )
        assert queue.acks == [["batch-1"]]
        assert (await session.scalars(select(UsageCounterModel.total_tokens))).all() == [23]

    async def test_recovers_lost_final_ack_response(self, session, replica, monkeypatch):
        queue = GatewayQueue(replica.ip_address, [batch()])
        acknowledge = queue.acknowledge_usage

        async def lose_response(ids):
            await acknowledge(ids)
            raise httpx.ReadError("Lost the Gateway's successful ACK response")

        monkeypatch.setattr(queue, "acknowledge_usage", lose_response)
        args = (queue.connection, replica.id, replica.gateway_id, replica.lock_token)
        assert not await usage.drain_gateway_usage(*args)
        assert queue.acks == [["batch-1"]] and queue.items == []
        assert await usage.drain_gateway_usage(*args)
        assert (await session.scalars(select(UsageCounterModel.total_tokens))).all() == [23]

    async def test_does_not_start_drain_for_stale_claim_or_different_gateway(
        self, replica, monkeypatch
    ):
        queue = GatewayQueue(replica.ip_address, [])
        calls = []

        async def empty():
            calls.append(True)
            return UsageDrainResponse(sealed=True, empty=True)

        monkeypatch.setattr(queue, "drain_usage", empty)
        assert not await usage.drain_gateway_usage(
            queue.connection, replica.id, replica.gateway_id, uuid.uuid4()
        )
        assert not await usage.drain_gateway_usage(
            queue.connection, replica.id, uuid.uuid4(), replica.lock_token
        )
        assert calls == []


@pytest.mark.asyncio
class TestCollectGatewayUsage:
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_commit_before_ack_and_retry_after_lost_ack(
        self, session, test_db, replica, monkeypatch
    ):
        queue = GatewayQueue(replica.ip_address, [batch()])
        sessions = []
        get_session = test_db.get_session

        def track_session(*args, **kwargs):
            db_session = get_session(*args, **kwargs)
            sessions.append(db_session)
            return db_session

        monkeypatch.setattr(test_db, "get_session", track_session)
        fetch = queue.fetch_usage_batches
        acknowledge = queue.acknowledge_usage
        transactions_during_io = []
        observed_at_ack = []

        async def tracked_fetch(limit):
            transactions_during_io.append(any(s.in_transaction() for s in sessions))
            return await fetch(limit)

        async def lose_first_ack(ids):
            transactions_during_io.append(any(s.in_transaction() for s in sessions))
            async with get_session() as observer:
                batches = (await observer.scalars(select(UsageBatchModel.batch_id))).all()
                counters = (await observer.scalars(select(UsageCounterModel.total_tokens))).all()
            observed_at_ack.append((ids, batches, counters))
            raise httpx.WriteError("ACK lost in transit")

        monkeypatch.setattr(queue, "fetch_usage_batches", tracked_fetch)
        monkeypatch.setattr(queue, "acknowledge_usage", lose_first_ack)
        await usage.collect_gateway_usage(queue.connection, replica.id, replica.lock_token)
        assert transactions_during_io == [False, False]
        assert observed_at_ack == [(["batch-1"], ["batch-1"], [23])]
        assert queue.items == [batch()]
        monkeypatch.setattr(queue, "acknowledge_usage", acknowledge)
        # A replacement worker fetches the already committed page from the Gateway.
        await claim(session, replica)
        await usage.collect_gateway_usage(queue.connection, replica.id, replica.lock_token)
        assert queue.fetches == 2
        assert queue.acks == [["batch-1"]]
        assert queue.items == []
        assert (await session.scalars(select(UsageCounterModel.total_tokens))).all() == [23]

    async def test_conflict_rolls_back_entire_page_without_ack(self, session, replica):
        await ingest_usage_batch(session, replica.id, replica.gateway_id, batch())
        await session.commit()
        items = [batch("new", offset=1), batch(tokens=4)]
        queue = GatewayQueue(replica.ip_address, items)
        await usage.collect_gateway_usage(queue.connection, replica.id, replica.lock_token)
        assert queue.fetches == 1
        assert queue.acks == []
        assert queue.items == items
        assert (await session.scalars(select(UsageBatchModel.batch_id))).all() == ["batch-1"]
        assert (await session.scalars(select(UsageCounterModel.total_tokens))).all() == [23]

    async def test_page_budget_leaves_remainder_for_next_poll(self, session, replica, monkeypatch):
        items = [batch(f"b-{i}", i) for i in range(5)]
        queue = GatewayQueue(replica.ip_address, items)
        monkeypatch.setattr(usage, "PAGE_SIZE", 2)
        monkeypatch.setattr(usage, "MAX_PAGES", 2)
        await usage.collect_gateway_usage(queue.connection, replica.id, replica.lock_token)
        assert queue.fetches == 2
        assert queue.acks == [["b-0", "b-1"], ["b-2", "b-3"]]
        assert queue.items == [items[4]]
        await usage.collect_gateway_usage(queue.connection, replica.id, replica.lock_token)
        assert queue.acks[-1] == ["b-4"]
        assert queue.items == []
        assert sorted(await session.scalars(select(UsageBatchModel.batch_id))) == [
            "b-0",
            "b-1",
            "b-2",
            "b-3",
            "b-4",
        ]

    async def test_timeout_during_fetch_leaves_page_pending(self, session, replica, monkeypatch):
        queue = GatewayQueue(replica.ip_address, [batch()])
        fetch = queue.fetch_usage_batches

        async def fetch_past_deadline(limit):
            page = await fetch(limit)
            loop = asyncio.get_running_loop()
            past_deadline = loop.time() + usage.COLLECTION_TIMEOUT + 1
            with monkeypatch.context() as clock:
                clock.setattr(loop, "time", lambda: past_deadline)
                # Let the loop dispatch its due timer before returning the page.
                await asyncio.sleep(0)
                await asyncio.sleep(0)
            return page

        monkeypatch.setattr(queue, "fetch_usage_batches", fetch_past_deadline)
        await usage.collect_gateway_usage(queue.connection, replica.id, replica.lock_token)
        assert queue.fetches == 1
        assert queue.acks == []
        assert queue.items == [batch()]
        assert (await session.scalars(select(UsageBatchModel))).all() == []

    @pytest.mark.parametrize("status_code", [404, 405])
    async def test_old_gateway_endpoint_skipped(self, replica, monkeypatch, caplog, status_code):
        queue = GatewayQueue(replica.ip_address, [batch()])

        async def unavailable(limit):
            queue.fetches += 1
            response = httpx.Response(
                status_code, request=httpx.Request("GET", "http://gateway/api/usage/batches")
            )
            response.raise_for_status()

        monkeypatch.setattr(queue, "fetch_usage_batches", unavailable)
        await usage.collect_gateway_usage(queue.connection, replica.id, replica.lock_token)
        assert queue.fetches == 1
        assert queue.acks == []
        queue.connection.try_collect_stats.assert_not_awaited()
        assert not any(
            r.levelno >= logging.WARNING and r.name == usage.__name__ for r in caplog.records
        )

    async def test_multiple_replicas_and_legacy_parent(self, session, replica):
        backend = await session.get(BackendModel, replica.backend_id)
        second = await create_gateway_replica(
            session, backend, gateway_id=replica.gateway_id, ip_address="2.2.2.2"
        )
        legacy = await create_gateway_replica(session, backend, ip_address="3.3.3.3")
        parent = await session.get(GatewayModel, replica.gateway_id)
        parent.gateway_replica_id = legacy.id
        await claim(session, second)
        await claim(session, legacy)
        for source in [replica, second, legacy]:
            queue = GatewayQueue(source.ip_address, [batch()])
            await usage.collect_gateway_usage(queue.connection, source.id, source.lock_token)
            assert queue.acks == [["batch-1"]]
        rows = (await session.scalars(select(UsageBatchModel))).all()
        assert {row.gateway_replica_id for row in rows} == {replica.id, second.id, legacy.id}
        assert {row.gateway_id for row in rows} == {parent.id}

    async def test_unbound_source_can_only_ack_historical_replay(self, session, replica):
        await ingest_usage_batch(session, replica.id, replica.gateway_id, batch())
        parent_id = replica.gateway_id
        replica.gateway_id = None
        await session.commit()
        queue = GatewayQueue(replica.ip_address, [batch()])
        await usage.collect_gateway_usage(queue.connection, replica.id, replica.lock_token)
        assert queue.acks == [["batch-1"]]
        queue.items = [batch("new", offset=1)]
        await usage.collect_gateway_usage(queue.connection, replica.id, replica.lock_token)
        assert queue.acks == [["batch-1"]]
        assert queue.items == [batch("new", offset=1)]
        row = (await session.scalars(select(UsageBatchModel))).one()
        assert row.batch_id == "batch-1" and row.gateway_id == parent_id

    async def test_ambiguous_address_is_skipped(self, session, replica):
        backend = await session.get(BackendModel, replica.backend_id)
        await create_gateway_replica(session, backend, ip_address=replica.ip_address)
        queue = GatewayQueue(replica.ip_address, [batch()])
        await usage.collect_gateway_usage(queue.connection, replica.id, replica.lock_token)
        assert queue.fetches == 0

    async def test_address_must_belong_to_claimed_replica(self, session, replica):
        backend = await session.get(BackendModel, replica.backend_id)
        other = await create_gateway_replica(
            session, backend, gateway_id=replica.gateway_id, ip_address="2.2.2.2"
        )
        # The pipeline gives all replicas claimed in one fetch the same token.
        other.lock_token = replica.lock_token
        other.lock_owner = replica.lock_owner
        other.lock_expires_at = replica.lock_expires_at
        await session.commit()
        queue = GatewayQueue(other.ip_address, [batch()])
        await usage.collect_gateway_usage(queue.connection, replica.id, replica.lock_token)
        assert queue.fetches == 0

    async def test_conflicting_modern_and_legacy_parents_are_skipped(self, session, replica):
        backend = await session.get(BackendModel, replica.backend_id)
        other_parent = await create_gateway(session, backend.project_id, backend.id, name="other")
        other_parent.gateway_replica_id = replica.id
        await session.commit()
        queue = GatewayQueue(replica.ip_address, [batch()])
        await usage.collect_gateway_usage(queue.connection, replica.id, replica.lock_token)
        assert queue.fetches == 0

    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_takeover_during_fetch_fences_stale_page(
        self, session, replica, monkeypatch, test_db
    ):
        queue = GatewayQueue(replica.ip_address, [batch()])
        fetch = queue.fetch_usage_batches

        async def fetch_then_take_over(limit):
            page = await fetch(limit)
            await claim(session, replica)
            return page

        monkeypatch.setattr(queue, "fetch_usage_batches", fetch_then_take_over)
        old_token = replica.lock_token
        await usage.collect_gateway_usage(queue.connection, replica.id, old_token)
        assert queue.fetches == 1
        assert queue.acks == []
        assert (await session.scalars(select(UsageBatchModel))).all() == []
        await session.commit()
        monkeypatch.setattr(queue, "fetch_usage_batches", fetch)
        await usage.collect_gateway_usage(queue.connection, replica.id, old_token)
        assert queue.fetches == 1
        await usage.collect_gateway_usage(queue.connection, replica.id, replica.lock_token)
        assert queue.acks == [["batch-1"]]
        assert (await session.scalars(select(UsageCounterModel.total_tokens))).all() == [23]


@pytest.mark.asyncio
class TestCollectGatewayUsageSQLiteLock:
    @pytest_asyncio.fixture
    async def sqlite_db(self, tmp_path):
        # Separate connections must see the same database to exercise SQLite's writer lock.
        db = Database(f"sqlite+aiosqlite:///{tmp_path / 'usage.db'}")
        try:
            async with db.engine.begin() as conn:
                await conn.run_sync(BaseModel.metadata.create_all)
            yield db
        finally:
            await db.engine.dispose()

    async def test_claim_cannot_change_between_revalidation_and_insert(
        self, session, replica, test_db, monkeypatch
    ):
        queue = GatewayQueue(replica.ip_address, [batch()])
        next_token = uuid.uuid4()
        takeover = (
            update(GatewayReplicaModel)
            .where(
                GatewayReplicaModel.id == replica.id,
                GatewayReplicaModel.lock_token == replica.lock_token,
            )
            .values(lock_token=next_token)
        )
        collisions = []
        async with test_db.engine.connect() as contender:
            await contender.exec_driver_sql("PRAGMA busy_timeout=0")

            async def ingest_with_competing_claim(*args):
                try:
                    await contender.execute(takeover)
                    await contender.commit()
                except OperationalError as exc:
                    assert isinstance(exc.orig, sqlite3.OperationalError)
                    collisions.append(exc.orig.sqlite_errorcode)
                    await contender.rollback()
                return await ingest_usage_batch(*args)

            monkeypatch.setattr(usage, "ingest_usage_batch", ingest_with_competing_claim)
            await usage.collect_gateway_usage(queue.connection, replica.id, replica.lock_token)
            assert collisions == [sqlite3.SQLITE_BUSY]
            assert queue.acks == [["batch-1"]]
            await contender.execute(takeover)
            await contender.commit()
        assert await session.scalar(select(GatewayReplicaModel.lock_token)) == next_token
        assert (await session.scalars(select(UsageCounterModel.total_tokens))).all() == [23]
