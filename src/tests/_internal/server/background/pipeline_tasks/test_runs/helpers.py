import datetime as dt
import uuid

from dstack._internal.server.background.pipeline_tasks.runs import (
    RunPipeline,
    RunPipelineItem,
)
from dstack._internal.server.models import RunModel

LOCK_EXPIRES_AT = dt.datetime(2025, 1, 2, 3, 4, tzinfo=dt.timezone.utc)


def run_to_pipeline_item(run_model: RunModel) -> RunPipelineItem:
    assert run_model.lock_token is not None
    assert run_model.lock_expires_at is not None
    return RunPipelineItem(
        __tablename__=run_model.__tablename__,
        id=run_model.id,
        lock_token=run_model.lock_token,
        lock_expires_at=run_model.lock_expires_at,
        prev_lock_expired=False,
        status=run_model.status,
    )


def lock_run(
    run_model: RunModel,
    *,
    lock_owner: str = RunPipeline.__name__,
    lock_expires_at: dt.datetime = LOCK_EXPIRES_AT,
) -> None:
    run_model.lock_token = uuid.uuid4()
    run_model.lock_expires_at = lock_expires_at
    run_model.lock_owner = lock_owner
