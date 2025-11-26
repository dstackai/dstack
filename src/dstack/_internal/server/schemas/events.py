import uuid
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.events import EventTargetType


class ListEventsRequest(CoreModel):
    # TODO: docs
    # TODO: restrict list length for filters?
    # TODO: forbid contradicting filters?
    target_projects: Optional[list[uuid.UUID]] = None
    target_users: Optional[list[uuid.UUID]] = None
    target_fleets: Optional[list[uuid.UUID]] = None
    target_instances: Optional[list[uuid.UUID]] = None
    target_runs: Optional[list[uuid.UUID]] = None
    target_jobs: Optional[list[uuid.UUID]] = None
    within_projects: Optional[list[uuid.UUID]] = None
    within_fleets: Optional[list[uuid.UUID]] = None
    within_runs: Optional[list[uuid.UUID]] = None
    include_target_types: Optional[list[EventTargetType]] = None
    actors: Optional[list[Optional[uuid.UUID]]] = None
    prev_recorded_at: Optional[datetime] = None
    prev_id: Optional[UUID] = None
    limit: int = Field(100, ge=1, le=100)
    ascending: bool = False
