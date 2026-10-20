import uuid

from sqlalchemy import false, or_, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.backends.features import BACKENDS_WITH_RESOURCE_LISTING_SUPPORT
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import (
    BackendModel,
    InstanceModel,
    JobModel,
    OrphanCleanupModel,
    ProjectModel,
)
from dstack._internal.server.utils import tracing
from dstack._internal.utils.common import get_current_datetime

_ENROLLMENT_BATCH_SIZE = 100


@tracing.instrument_scheduled_task
async def enroll_backends_in_orphan_cleanup():
    """
    Creates `OrphanCleanupModel` rows for backends that support resource listing,
    so that `OrphanCleanupPipeline` starts processing them.

    Only backends of projects with instances or jobs that have `provider_ref` are enrolled,
    since other backends cannot have orphaned resources that can be matched.

    At most `_ENROLLMENT_BATCH_SIZE` backends are enrolled per run. This spreads out
    the first cleanups when many backends become eligible at once, e.g. after an upgrade.
    """
    async with get_session_ctx() as session:
        backend_ids = await _select_backend_ids_to_enroll(session)
        if len(backend_ids) == 0:
            return
        now = get_current_datetime()
        await session.execute(
            # Another replica may enroll the same backends concurrently
            _insert(OrphanCleanupModel)
            .values(
                [
                    {
                        "id": uuid.uuid4(),
                        "backend_id": backend_id,
                        "created_at": now,
                        "last_processed_at": now,
                    }
                    for backend_id in backend_ids
                ]
            )
            .on_conflict_do_nothing(index_elements=[OrphanCleanupModel.backend_id])
        )


async def _select_backend_ids_to_enroll(session: AsyncSession) -> list[uuid.UUID]:
    has_instances_with_provider_ref = (
        select(InstanceModel.id)
        .where(
            InstanceModel.project_id == BackendModel.project_id,
            InstanceModel.provider_ref.is_not(None),
        )
        .exists()
    )
    has_jobs_with_provider_ref = (
        select(JobModel.id)
        .where(
            JobModel.project_id == BackendModel.project_id,
            JobModel.provider_ref.is_not(None),
        )
        .exists()
    )
    is_enrolled = (
        select(OrphanCleanupModel.id)
        .where(OrphanCleanupModel.backend_id == BackendModel.id)
        .exists()
    )
    res = await session.execute(
        select(BackendModel.id)
        .join(ProjectModel, ProjectModel.id == BackendModel.project_id)
        .where(
            ProjectModel.deleted == false(),
            BackendModel.type.in_(BACKENDS_WITH_RESOURCE_LISTING_SUPPORT),
            ~is_enrolled,
            or_(has_instances_with_provider_ref, has_jobs_with_provider_ref),
        )
        .limit(_ENROLLMENT_BATCH_SIZE)
    )
    return list(res.scalars().all())


def _insert(model: type[OrphanCleanupModel]):
    # The generic `sqlalchemy.insert()` does not support `ON CONFLICT`.
    # Postgres and SQLite inserts both provide `on_conflict_do_nothing()`.
    if get_db().dialect_name == "postgresql":
        return postgresql.insert(model)
    return sqlite.insert(model)
