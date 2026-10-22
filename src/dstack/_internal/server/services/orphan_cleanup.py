import uuid
from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, or_, select, true
from sqlalchemy.orm import InstrumentedAttribute

from dstack._internal.core.backends.features import get_backends_with_resource_listing_support
from dstack._internal.core.models.backends.orphans import OrphanCleanupMode
from dstack._internal.server import settings
from dstack._internal.server.models import BackendModel, OrphanCleanupModel
from dstack._internal.utils.common import get_current_datetime

CLEANUP_RETRY_INTERVAL_MULTIPLIERS = [2, 6, 24]
"""Retry delays after failed cleanups, as multiples of the cleanup interval."""

_MAX_WAIT_RETRY_DELAYS = 7
"""
How long records wait for a clean run, as a multiple of the longest retry delay
(a week with the default 1-hour cleanup interval). It gives backends whose cleanups
keep failing a few attempts, while a backend that is never cleaned up
(e.g. a region that always fails to list) does not keep records forever.
"""


def get_cleaned_up_after_filter(
    project_id: InstrumentedAttribute[uuid.UUID], at: InstrumentedAttribute[datetime]
) -> ColumnElement[bool]:
    """
    Returns a filter that is true if orphan cleanup has had a clean run started after `at`
    for every backend of the project that supports resource listing, i.e. orphaned resources
    of records that finished before `at` have been reported or deleted.
    Backends not enrolled in orphan cleanup yet count as not cleaned up.
    Also true if `at` is older than the max wait (see `_MAX_WAIT_RETRY_DELAYS`).
    Always true if orphan cleanup is off.

    A clean run in report mode counts too, although its orphans were only reported.
    So after switching to delete mode, orphans of records deleted based on this filter
    are not matched and stay.
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
    max_wait = (
        _MAX_WAIT_RETRY_DELAYS
        * CLEANUP_RETRY_INTERVAL_MULTIPLIERS[-1]
        * timedelta(seconds=settings.ORPHAN_CLEANUP_INTERVAL_SECONDS)
    )
    return or_(~has_backend_not_cleaned_up, at < get_current_datetime() - max_wait)
