import datetime as dt
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.server.background.pipeline_tasks.instances import (
    InstancePipeline,
    InstancePipelineItem,
    InstanceWorker,
)
from dstack._internal.server.models import InstanceModel

LOCK_EXPIRES_AT = dt.datetime(2025, 1, 2, 3, 4, tzinfo=dt.timezone.utc)


def instance_to_pipeline_item(instance_model: InstanceModel) -> InstancePipelineItem:
    assert instance_model.lock_token is not None
    assert instance_model.lock_expires_at is not None
    return InstancePipelineItem(
        __tablename__=instance_model.__tablename__,
        id=instance_model.id,
        lock_token=instance_model.lock_token,
        lock_expires_at=instance_model.lock_expires_at,
        prev_lock_expired=False,
        status=instance_model.status,
    )


def lock_instance(instance_model: InstanceModel) -> None:
    instance_model.lock_token = uuid.uuid4()
    instance_model.lock_expires_at = LOCK_EXPIRES_AT
    instance_model.lock_owner = InstancePipeline.__name__


async def process_instance(
    session: AsyncSession, worker: InstanceWorker, instance_model: InstanceModel
) -> None:
    lock_instance(instance_model)
    await session.commit()
    await worker.process(instance_to_pipeline_item(instance_model))
