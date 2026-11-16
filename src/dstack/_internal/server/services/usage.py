"""Transactional receipt of Gateway minute counters; no pricing or quota decisions."""

import json
import uuid
from dataclasses import dataclass

from sqlalchemy import insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.proxy.lib.schemas.usage import UsageBatch
from dstack._internal.server.models import UsageBatchModel, UsageCollectorModel, UsageCounterModel


class UsageConflict(ValueError):
    """Identity or immutable content changed: preserve the source for reconciliation."""


@dataclass(frozen=True)
class ReceiptResult:
    batch_id: str
    inserted: bool
    """Caller must commit before using this result to ACK."""


async def ingest_usage_batch(
    session: AsyncSession, gateway_replica_id: uuid.UUID, collector_id: str, batch: UsageBatch
) -> ReceiptResult:
    # Validate even callers that constructed an unchecked model_copy().
    batch = UsageBatch.model_validate(batch.model_dump())
    if not collector_id or len(collector_id) > 128:
        raise ValueError("Invalid collector identity")
    content = batch.model_dump(mode="json")
    content["entries"].sort(key=lambda entry: (entry["consumer_subject_id"], entry["service_id"]))
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
    for entry in batch.entries:
        for name in (
            "prompt_tokens",
            "cached_prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "unknown_usage_attempts",
        ):
            if getattr(entry, name) > 2**63 - 1:
                raise ValueError("Usage counter exceeds signed 64-bit storage")

    dialect_insert = (
        pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
    )
    # INSERT first avoids a read-to-write upgrade and handles cross-process races in Postgres.
    await session.execute(
        dialect_insert(UsageCollectorModel)
        .values(collector_id=collector_id, gateway_replica_id=gateway_replica_id)
        .on_conflict_do_nothing()
    )
    owner = await session.scalar(
        select(UsageCollectorModel.gateway_replica_id).where(
            UsageCollectorModel.collector_id == collector_id
        )
    )
    if owner != gateway_replica_id:
        raise UsageConflict("Collector identity reset or moved to another Gateway")

    receipt_id = uuid.uuid4()
    created = await session.scalar(
        dialect_insert(UsageBatchModel)
        .values(
            id=receipt_id,
            collector_id=collector_id,
            batch_id=batch.batch_id,
            interval_start=batch.interval_start,
            interval_end=batch.interval_end,
            content=canonical,
        )
        .on_conflict_do_nothing()
        .returning(UsageBatchModel.id)
    )
    if created is None:
        existing = await session.scalar(
            select(UsageBatchModel.content).where(
                UsageBatchModel.collector_id == collector_id,
                UsageBatchModel.batch_id == batch.batch_id,
            )
        )
        if existing != canonical:
            raise UsageConflict("Conflicting batch content or duplicate minute under a new ID")
        return ReceiptResult(batch.batch_id, inserted=False)
    if batch.entries:
        await session.execute(
            insert(UsageCounterModel),
            [{"receipt_id": receipt_id, **entry.model_dump()} for entry in batch.entries],
        )
    return ReceiptResult(batch.batch_id, inserted=True)
