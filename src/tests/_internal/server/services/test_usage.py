import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from dstack._internal.proxy.lib.schemas.usage import UsageBatch, UsageEntry
from dstack._internal.server.models import UsageBatchModel, UsageCollectorModel, UsageCounterModel
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
    item = batch(tokens=2**40)
    async with test_db.get_session() as session:
        assert (await ingest_usage_batch(session, gateway, "collector", item)).inserted
        await session.commit()
    async with test_db.get_session() as session:
        assert not (await ingest_usage_batch(session, gateway, "collector", item)).inserted
        await session.commit()
    async with test_db.get_session() as session:
        with pytest.raises(UsageConflict):
            await ingest_usage_batch(session, gateway, "collector", batch(tokens=4))
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
        await ingest_usage_batch(session, uuid.uuid4(), "collector", batch())
        await session.rollback()
    async with test_db.get_session() as session:
        for model in [UsageCollectorModel, UsageBatchModel, UsageCounterModel]:
            assert await session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
async def test_identity_and_interval_conflicts(test_db):
    gateway = uuid.uuid4()
    async with test_db.get_session() as session:
        await ingest_usage_batch(session, gateway, "collector", batch())
        await session.commit()
    for g, c, b in [
        (uuid.uuid4(), "collector", batch()),
        (gateway, "reset", batch()),
        (gateway, "collector", batch("duplicate-minute")),
    ]:
        async with test_db.get_session() as session:
            with pytest.raises(UsageConflict):
                await ingest_usage_batch(session, g, c, b)
            await session.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["postgres"], indirect=True)
async def test_concurrent_pollers_commit_once(test_db):
    gateway = uuid.uuid4()

    async def ingest():
        async with test_db.get_session() as session:
            result = await ingest_usage_batch(session, gateway, "collector", batch())
            await session.commit()
            return result.inserted

    assert sorted(await asyncio.gather(ingest(), ingest())) == [False, True]
    async with test_db.get_session() as session:
        assert await session.scalar(select(func.count()).select_from(UsageCounterModel)) == 1
