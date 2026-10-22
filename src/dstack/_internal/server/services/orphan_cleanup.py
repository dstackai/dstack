import uuid
from datetime import datetime

from sqlalchemy import ColumnElement, or_, select, true
from sqlalchemy.orm import InstrumentedAttribute

from dstack._internal.core.backends.features import get_backends_with_resource_listing_support
from dstack._internal.core.models.backends.orphans import OrphanCleanupMode
from dstack._internal.server import settings
from dstack._internal.server.models import BackendModel, OrphanCleanupModel


def get_cleaned_up_after_filter(
    project_id: InstrumentedAttribute[uuid.UUID], at: InstrumentedAttribute[datetime]
) -> ColumnElement[bool]:
    """
    Returns a filter that is true if orphan cleanup has had a clean run started after `at`
    for every backend of the project that supports resource listing, i.e. orphaned resources
    of records that finished before `at` have been reported or deleted.
    Backends not enrolled in orphan cleanup yet are not cleaned up.
    Always true if orphan cleanup is off.
    """
    if settings.ORPHAN_CLEANUP_MODE == OrphanCleanupMode.OFF:
        return true()
    # `clean_at` is set to the start of the clean listing minus a margin for timing
    # inaccuracies, so `clean_at > at` means the listing started after `at`.
    has_backend_not_cleaned_up = (
        select(BackendModel.id)
        .outerjoin(OrphanCleanupModel, OrphanCleanupModel.backend_id == BackendModel.id)
        .where(
            BackendModel.project_id == project_id,
            BackendModel.type.in_(get_backends_with_resource_listing_support()),
            or_(OrphanCleanupModel.clean_at.is_(None), OrphanCleanupModel.clean_at <= at),
        )
        .exists()
    )
    return ~has_backend_not_cleaned_up
