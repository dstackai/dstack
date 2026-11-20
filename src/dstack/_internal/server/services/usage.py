"""Transactional receipt of Gateway minute counters."""

import uuid
from dataclasses import dataclass

from sqlalchemy import insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.proxy.lib.schemas.usage import UsageBatch
from dstack._internal.server.models import UsageBatchModel
from dstack._internal.utils.common import get_current_datetime

_COUNTER_FIELDS = (
    "prompt_tokens",
    "cached_prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "unknown_usage_attempts",
)
_MAX_COUNTER = 2**63 - 1


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
    entries = _normalize_entries(batch)
    if gateway_id is not None:
        dialect_insert = (
            pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
        )
        received_at = get_current_datetime()
        rows = [
            {
                "id": uuid.uuid4(),
                "gateway_replica_id": gateway_replica_id,
                "gateway_id": gateway_id,
                "batch_id": batch.batch_id,
                "interval_start": batch.interval_start,
                "interval_end": batch.interval_end,
                "received_at": received_at,
                "batch_row_number": number,
                "user_id": user_id,
                "run_id": run_id,
                **counters,
            }
            for number, ((user_id, run_id), counters) in enumerate(sorted(entries.items()))
        ]
        # Row zero claims both delivery keys. A conflict can wait for a competing
        # transaction and must be resolved against its entire committed batch.
        created = await session.scalar(
            dialect_insert(UsageBatchModel)
            .values(rows[0])
            .on_conflict_do_nothing()
            .returning(UsageBatchModel.id)
        )
        if created is not None:
            if len(rows) > 1:
                await session.execute(insert(UsageBatchModel), rows[1:])
            return ReceiptResult(batch.batch_id, inserted=True)

    existing = (
        await session.scalars(
            select(UsageBatchModel).where(
                UsageBatchModel.gateway_replica_id == gateway_replica_id,
                UsageBatchModel.batch_id == batch.batch_id,
            )
        )
    ).all()
    for row in existing:
        if gateway_id is not None and row.gateway_id != gateway_id:
            raise UsageConflict("Historical Gateway identity cannot change")
        if row.interval_start != batch.interval_start or row.interval_end != batch.interval_end:
            raise UsageConflict("Historical batch interval cannot change")
    stored_entries = {
        (row.user_id, row.run_id): {name: getattr(row, name) for name in _COUNTER_FIELDS}
        for row in existing
    }
    if stored_entries != entries:
        raise UsageConflict("Missing source, conflicting content or duplicate minute")
    return ReceiptResult(batch.batch_id, inserted=False)


def _normalize_entries(batch: UsageBatch) -> dict[tuple[uuid.UUID, uuid.UUID], dict[str, int]]:
    if not batch.entries:
        raise ValueError("Usage batch must contain at least one entry")
    entries = {}
    for entry in batch.entries:
        try:
            key = uuid.UUID(entry.consumer_subject_id), uuid.UUID(entry.service_id)
        except ValueError as exc:
            raise ValueError("Usage entry requires valid user and run UUIDs") from exc
        if key in entries:
            raise ValueError("Duplicate usage key after UUID normalization")
        counters = {name: getattr(entry, name) for name in _COUNTER_FIELDS}
        if any(value > _MAX_COUNTER for value in counters.values()):
            raise ValueError("Usage counter exceeds signed 64-bit storage")
        entries[key] = counters
    return entries
