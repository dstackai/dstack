"""Active-run analysis and transition helpers for the run pipeline."""

import uuid
from dataclasses import dataclass

from dstack._internal.core.models.runs import RunStatus


@dataclass
class ActiveContext:
    run_id: uuid.UUID
    status: RunStatus


async def process_active_run(context: ActiveContext) -> None:
    raise NotImplementedError(
        f"Run pipeline active path is not implemented yet for run {context.run_id}"
    )
