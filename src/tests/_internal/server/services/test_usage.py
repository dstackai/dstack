import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from dstack._internal.proxy.lib.schemas.usage import UsageBatch, UsageEntry
from dstack._internal.server.models import GatewayModel, RunModel, UsageBatchModel, UserModel
from dstack._internal.server.services.usage import UsageConflict, ingest_usage_batch
from dstack._internal.server.services.users import delete_users
from dstack._internal.server.testing.common import (
    create_backend,
    create_gateway,
    create_project,
    create_repo,
    create_run,
    create_user,
)

RUN_ID = uuid.UUID("a" * 32)
OTHER_RUN_ID = uuid.UUID("b" * 32)


def entry(user_id, run_id=RUN_ID, prompt=20, cached=5, completion=3, unknown=0):
    return UsageEntry(
        consumer_subject_id=user_id.hex,
        service_id=run_id.hex,
        prompt_tokens=prompt,
        cached_prompt_tokens=cached,
        completion_tokens=completion,
        total_tokens=prompt + completion,
        unknown_usage_attempts=unknown,
    )


def batch(user_id, batch_id="batch-1", offset=0, tokens=3, *, entries=None):
    start = datetime(2026, 11, 20, 10, tzinfo=timezone.utc) + timedelta(minutes=offset)
    return UsageBatch(
        batch_id=batch_id,
        interval_start=start,
        interval_end=start + timedelta(minutes=1),
        entries=[entry(user_id, completion=tokens)] if entries is None else entries,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestIngestUsageBatch:
    async def test_numbered_rows_and_reordered_replay(self, session):
        user = await create_user(session)
        other = await create_user(session, name="another")
        replica, parent = uuid.uuid4(), uuid.uuid4()
        first = entry(user.id, prompt=15, cached=3, completion=5)
        second = entry(user.id, OTHER_RUN_ID, prompt=5, cached=0, completion=2)
        unknown = entry(other.id, prompt=0, cached=0, completion=0, unknown=1)
        item = batch(user.id, entries=[second, first])
        next_minute = batch(user.id, "next-minute", offset=1, entries=[unknown, first])
        assert (await ingest_usage_batch(session, replica, parent, item)).inserted
        assert (await ingest_usage_batch(session, replica, parent, next_minute)).inserted
        await session.commit()

        rows = (
            await session.scalars(
                select(UsageBatchModel).order_by(
                    UsageBatchModel.interval_start, UsageBatchModel.batch_row_number
                )
            )
        ).all()
        assert [row.batch_row_number for row in rows] == [0, 1, 0, 1]
        assert [(row.user_id, row.run_id, row.total_tokens) for row in rows[:2]] == [
            (user.id, RUN_ID, 20),
            (user.id, OTHER_RUN_ID, 7),
        ]
        assert sum(row.total_tokens for row in rows[:2]) == 27
        assert rows[0].received_at == rows[1].received_at
        assert [(row.user_id, row.unknown_usage_attempts) for row in rows[2:]] == sorted(
            [(user.id, 0), (other.id, 1)]
        )
        assert len({row.id for row in rows}) == 4
        replay = batch(
            user.id,
            entries=[
                first.model_copy(update={"consumer_subject_id": str(user.id).upper()}),
                second.model_copy(update={"service_id": str(OTHER_RUN_ID).upper()}),
            ],
        )
        assert not (await ingest_usage_batch(session, replica, parent, replay)).inserted
        await session.commit()
        persisted = (
            await session.scalars(
                select(UsageBatchModel).order_by(
                    UsageBatchModel.interval_start, UsageBatchModel.batch_row_number
                )
            )
        ).all()
        assert persisted == rows

    async def test_identity_interval_and_content_conflicts(self, session):
        user = await create_user(session)
        replica, parent = uuid.uuid4(), uuid.uuid4()
        first = entry(user.id, completion=2**40)
        second = entry(user.id, OTHER_RUN_ID)
        third = entry(user.id, uuid.uuid4())
        original = batch(user.id, entries=[first, second])
        await ingest_usage_batch(session, replica, parent, original)
        await session.commit()
        for gateway, item in [
            (uuid.uuid4(), original),
            (parent, batch(user.id, offset=1, entries=[first, second])),
            (parent, batch(user.id, entries=[first])),
            (parent, batch(user.id, entries=[first, second, third])),
            (
                parent,
                batch(
                    user.id,
                    entries=[first, second.model_copy(update={"unknown_usage_attempts": 1})],
                ),
            ),
            (parent, batch(user.id, "duplicate-minute", entries=[third])),
        ]:
            with pytest.raises(UsageConflict):
                await ingest_usage_batch(session, replica, gateway, item)
            await session.rollback()

        assert (await ingest_usage_batch(session, uuid.uuid4(), parent, original)).inserted
        await session.commit()
        assert await session.scalar(select(func.count()).select_from(UsageBatchModel)) == 4
        assert await session.scalar(select(func.sum(UsageBatchModel.total_tokens))) == 2 * (
            2**40 + 43
        )

    @pytest.mark.parametrize("field", ["consumer_subject_id", "service_id"])
    async def test_rejects_malformed_uuid(self, session, field):
        user = await create_user(session)
        item = batch(user.id, entries=[entry(user.id).model_copy(update={field: "malformed"})])
        with pytest.raises(ValueError, match="UUID"):
            await ingest_usage_batch(session, uuid.uuid4(), uuid.uuid4(), item)
        assert await session.scalar(select(func.count()).select_from(UsageBatchModel)) == 0

    @pytest.mark.parametrize("invalid", ["duplicate", "overflow", "empty"])
    async def test_rejects_invalid_entries(self, session, invalid):
        user = await create_user(session)
        first = entry(user.id)
        entries, message = {
            "duplicate": (
                [first, first.model_copy(update={"service_id": str(RUN_ID)})],
                "Duplicate",
            ),
            "overflow": ([entry(user.id, unknown=2**63)], "signed 64-bit"),
            "empty": ([], "entry"),
        }[invalid]
        with pytest.raises(ValueError, match=message):
            await ingest_usage_batch(
                session, uuid.uuid4(), uuid.uuid4(), batch(user.id, entries=entries)
            )
        assert await session.scalar(select(func.count()).select_from(UsageBatchModel)) == 0

    async def test_remaining_insert_failure_rolls_back_row_zero(self, session):
        user = await create_user(session)
        missing = uuid.UUID(int=2**128 - 1)
        user_id = user.id
        assert user_id < missing
        replica, parent = uuid.uuid4(), uuid.uuid4()
        item = batch(user_id, entries=[entry(user_id), entry(missing)])
        with pytest.raises(IntegrityError, match="FOREIGN KEY|foreign key"):
            await ingest_usage_batch(session, replica, parent, item)
        await session.rollback()
        assert await session.scalar(select(func.count()).select_from(UsageBatchModel)) == 0
        assert (await ingest_usage_batch(session, replica, parent, batch(user_id))).inserted
        await session.commit()

    async def test_history_survives_deleted_run_gateway_and_soft_deleted_user(self, session):
        user = await create_user(session)
        admin = await create_user(session, name="another")
        project = await create_project(session, owner=user)
        repo = await create_repo(session, project_id=project.id)
        backend = await create_backend(session, project.id)
        gateway = await create_gateway(session, project.id, backend.id)
        run = await create_run(session, project, repo, user, gateway=gateway)
        replica, parent, user_id, run_id = uuid.uuid4(), gateway.id, user.id, run.id
        item = batch(user_id, entries=[entry(user_id, run_id)])
        await ingest_usage_batch(session, replica, parent, item)
        await session.commit()
        await session.execute(delete(RunModel).where(RunModel.id == run_id))
        await delete_users(session, admin, [user.name])
        await session.commit()
        assert user.deleted and not user.active

        delayed = batch(user_id, "next-minute", offset=1, entries=[entry(user_id, run_id)])
        assert (await ingest_usage_batch(session, replica, parent, delayed)).inserted
        await session.commit()
        await session.execute(delete(GatewayModel).where(GatewayModel.id == parent))
        await session.commit()

        assert not (await ingest_usage_batch(session, replica, None, item)).inserted
        with pytest.raises(UsageConflict):
            await ingest_usage_batch(session, replica, None, batch(user_id, "new", offset=2))
        report = select(func.sum(UsageBatchModel.total_tokens)).where(
            UsageBatchModel.gateway_id == parent,
            UsageBatchModel.user_id == user_id,
            UsageBatchModel.run_id == run_id,
        )
        assert await session.scalar(report) == 46
        with pytest.raises(IntegrityError, match="FOREIGN KEY|foreign key"):
            await session.execute(delete(UserModel).where(UserModel.id == user_id))
        await session.rollback()
        assert await session.scalar(report) == 46


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["postgres"], indirect=True)
@pytest.mark.parametrize("competing_minute", [False, True])
async def test_concurrent_pollers_commit_once(test_db, session, competing_minute):
    user = await create_user(session)
    replica, parent = uuid.uuid4(), uuid.uuid4()
    first, second = entry(user.id), entry(user.id, OTHER_RUN_ID)
    original = batch(user.id, entries=[first, second])
    contender = (
        batch(user.id, "competing-minute", entries=[entry(user.id, uuid.uuid4())])
        if competing_minute
        else batch(user.id, entries=[second, first])
    )

    assert (await ingest_usage_batch(session, replica, parent, original)).inserted
    contender_pid = asyncio.get_running_loop().create_future()

    async def ingest():
        async with test_db.get_session() as other:
            contender_pid.set_result(await other.scalar(select(func.pg_backend_pid())))
            result = await ingest_usage_batch(other, replica, parent, contender)
            await other.commit()
            return result.inserted

    async def receive():
        if competing_minute:
            with pytest.raises(UsageConflict):
                await ingest()
        else:
            assert not await ingest()

    winner_pid = await session.scalar(select(func.pg_backend_pid()))
    async with asyncio.timeout(5), asyncio.TaskGroup() as tasks:
        tasks.create_task(receive())
        pid = await contender_pid
        blockers = select(func.pg_blocking_pids(pid))
        async with test_db.get_session() as observer:
            while winner_pid not in (await observer.scalar(blockers)):
                pass
        await session.commit()
    assert await session.scalar(select(func.count()).select_from(UsageBatchModel)) == 2
    assert await session.scalar(select(func.sum(UsageBatchModel.total_tokens))) == 46
