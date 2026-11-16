import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from dstack._internal.proxy.lib.schemas.usage import UsageBatch, UsageEntry
from dstack._internal.server.models import UsageBatchModel, UsageCounterModel
from dstack._internal.server.services.usage import UsageConflict, ingest_usage_batch


def batch(batch_id="batch-1", offset=0, tokens=3):
    start = datetime(2026, 11, 16, 10, tzinfo=timezone.utc) + timedelta(minutes=offset)
    return UsageBatch(
        batch_id=batch_id,
        interval_start=start,
        interval_end=start + timedelta(minutes=1),
        entries=[
            UsageEntry(
                consumer_subject_id="1" * 32,
                service_id="a" * 32,
                prompt_tokens=20,
                cached_prompt_tokens=5,
                completion_tokens=tokens,
                total_tokens=20 + tokens,
            )
        ],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
async def test_commit_replay_conflict_and_historical_ids(test_db):
    gateway = uuid.uuid4()
    parent = uuid.uuid4()
    item = batch(tokens=2**40)
    async with test_db.get_session() as session:
        assert (await ingest_usage_batch(session, gateway, parent, item)).inserted
        await session.commit()
    async with test_db.get_session() as session:
        assert not (await ingest_usage_batch(session, gateway, parent, item)).inserted
        await session.commit()
    async with test_db.get_session() as session:
        with pytest.raises(UsageConflict):
            await ingest_usage_batch(session, gateway, parent, batch(tokens=4))
        await session.rollback()
        row = (await session.scalars(select(UsageCounterModel))).one()
        assert row.completion_tokens == 2**40
        assert row.consumer_subject_id == "1" * 32 and row.service_id == "a" * 32
        assert await session.scalar(select(func.count()).select_from(UsageBatchModel)) == 1
        # Historical attribution is retained even without corresponding live user/run rows.


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
async def test_rollback_leaves_no_receipt_or_entries(test_db):
    async with test_db.get_session() as session:
        await ingest_usage_batch(session, uuid.uuid4(), uuid.uuid4(), batch())
        await session.rollback()
    async with test_db.get_session() as session:
        for model in [UsageBatchModel, UsageCounterModel]:
            assert await session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
async def test_identity_and_interval_conflicts(test_db):
    gateway = uuid.uuid4()
    parent = uuid.uuid4()
    async with test_db.get_session() as session:
        await ingest_usage_batch(session, gateway, parent, batch())
        await session.commit()
    for parent_id, item in [(uuid.uuid4(), batch()), (parent, batch("duplicate-minute"))]:
        async with test_db.get_session() as session:
            with pytest.raises(UsageConflict):
                await ingest_usage_batch(session, gateway, parent_id, item)
            await session.rollback()
    # An independent replica may legitimately use the same batch ID and minute.
    async with test_db.get_session() as session:
        assert (await ingest_usage_batch(session, uuid.uuid4(), parent, batch())).inserted
        await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["postgres"], indirect=True)
async def test_concurrent_pollers_commit_once(test_db):
    gateway = uuid.uuid4()
    parent = uuid.uuid4()

    async def ingest():
        async with test_db.get_session() as session:
            result = await ingest_usage_batch(session, gateway, parent, batch())
            await session.commit()
            return result.inserted

    assert sorted(await asyncio.gather(ingest(), ingest())) == [False, True]
    async with test_db.get_session() as session:
        assert await session.scalar(select(func.count()).select_from(UsageCounterModel)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
async def test_history_snapshot_missing_parent_and_renamed_link(test_db):
    replica, parent = uuid.uuid4(), uuid.uuid4()
    async with test_db.get_session() as session:
        await ingest_usage_batch(session, replica, parent, batch())
        await session.commit()
    async with test_db.get_session() as session:
        assert not (await ingest_usage_batch(session, replica, None, batch())).inserted
        row = (await session.scalars(select(UsageBatchModel))).one()
        counter = (await session.scalars(select(UsageCounterModel))).one()
        assert row.gateway_replica_id == replica
        assert row.gateway_id == parent
        assert counter.usage_baches_id == row.id
        # No live infrastructure rows are needed to read the receipt's source.
        assert counter.total_tokens == 23
        with pytest.raises(UsageConflict):
            await ingest_usage_batch(session, replica, None, batch("new", offset=1))
        await session.rollback()
    async with test_db.get_session() as session:
        row = (await session.scalars(select(UsageBatchModel))).one()
        row.gateway_id = None  # Represents unresolved pre-upgrade history.
        await session.commit()
    async with test_db.get_session() as session:
        assert not (await ingest_usage_batch(session, replica, parent, batch())).inserted
        row = (await session.scalars(select(UsageBatchModel))).one()
        assert row.gateway_id is None  # Replay cannot silently rewrite history.
