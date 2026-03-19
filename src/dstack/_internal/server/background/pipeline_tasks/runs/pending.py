"""Pending-run processing helpers for the run pipeline."""

import uuid
from dataclasses import dataclass


@dataclass
class PendingContext:
    run_id: uuid.UUID


async def process_pending_run(context: PendingContext) -> None:
    raise NotImplementedError(
        f"Run pipeline pending path is not implemented yet for run {context.run_id}"
    )
