import uuid

from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.backends.features import get_backends_with_resource_listing_support
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import (
    BackendModel,
    OrphanCleanupModel,
    ProjectModel,
    ProviderRefModel,
)
from dstack._internal.server.utils import tracing
from dstack._internal.utils.common import get_current_datetime

_ENROLLMENT_BATCH_SIZE = 100


@tracing.instrument_scheduled_task
async def enroll_backends_in_orphan_cleanup():
    """
    Creates `OrphanCleanupModel` rows for backends that support resource listing,
    so that `OrphanCleanupPipeline` starts processing them.

    Only backends of projects that have issued `provider_ref`s are enrolled,
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
    has_provider_refs = (
        select(ProviderRefModel.provider_ref)
        .where(ProviderRefModel.project_id == BackendModel.project_id)
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
            ProjectModel.deleted == False,
            BackendModel.type.in_(get_backends_with_resource_listing_support()),
            ~is_enrolled,
            has_provider_refs,
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
