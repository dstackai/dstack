"""Transactional receipt of Gateway minute counters; no pricing or quota decisions."""

import json
import uuid
from dataclasses import dataclass

from sqlalchemy import insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.proxy.lib.schemas.usage import UsageBatch
from dstack._internal.server.models import UsageBatchModel, UsageCounterModel


class UsageConflict(ValueError):
    """Identity or immutable content changed: preserve the source for reconciliation."""


@dataclass(frozen=True)
class ReceiptResult:
    batch_id: str
    inserted: bool
    """Caller must commit before using this result to ACK."""


async def ingest_usage_batch(
    session: AsyncSession,
    gateway_replica_id: uuid.UUID,
    gateway_id: uuid.UUID | None,
    batch: UsageBatch,
) -> ReceiptResult:
    # Validate even callers that constructed an unchecked model_copy().
    batch = UsageBatch.model_validate(batch.model_dump())
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
    batch_record_id = uuid.uuid4()
    created = None
    if gateway_id is not None:
        # INSERT first avoids SQLite read-to-write upgrades and serializes PG conflicts.
        created = await session.scalar(
            dialect_insert(UsageBatchModel)
            .values(
                id=batch_record_id,
                gateway_replica_id=gateway_replica_id,
                gateway_id=gateway_id,
                batch_id=batch.batch_id,
                interval_start=batch.interval_start,
                interval_end=batch.interval_end,
                content=canonical,
            )
            .on_conflict_do_nothing()
            .returning(UsageBatchModel.id)
        )
    if created is None:
        existing = (
            await session.execute(
                select(UsageBatchModel.content, UsageBatchModel.gateway_id).where(
                    UsageBatchModel.gateway_replica_id == gateway_replica_id,
                    UsageBatchModel.batch_id == batch.batch_id,
                )
            )
        ).one_or_none()
        if existing is None or existing.content != canonical:
            raise UsageConflict("Missing source, conflicting content or duplicate minute")
        if gateway_id is not None and existing.gateway_id not in (None, gateway_id):
            raise UsageConflict("Historical Gateway identity cannot change")
        return ReceiptResult(batch.batch_id, inserted=False)
    if batch.entries:
        await session.execute(
            insert(UsageCounterModel),
            [
                {"usage_baches_id": batch_record_id, **entry.model_dump()}
                for entry in batch.entries
            ],
        )
    return ReceiptResult(batch.batch_id, inserted=True)
