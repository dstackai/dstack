# TODO: docs

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from dstack._internal.core.models.common import CoreModel


class EventTargetType(str, Enum):
    PROJECT = "project"
    USER = "user"
    FLEET = "fleet"
    INSTANCE = "instance"
    RUN = "run"
    JOB = "job"


class EventTarget(CoreModel):
    type: str  # Holds EventTargetType; str for adding new types without breaking compatibility
    project_id: Optional[uuid.UUID]
    id: uuid.UUID
    name: str


class Event(CoreModel):
    id: uuid.UUID
    message: str
    recorded_at: datetime
    actor_user_id: Optional[uuid.UUID]
    actor_user: Optional[str]
    targets: list[EventTarget]
