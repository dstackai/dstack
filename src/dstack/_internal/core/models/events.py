import uuid
from datetime import datetime
from enum import Enum
from typing import Annotated, Optional

from pydantic import Field

from dstack._internal.core.models.common import CoreModel
from dstack._internal.utils.common import list_enum_values_for_annotation


class EventTargetType(str, Enum):
    PROJECT = "project"
    USER = "user"
    FLEET = "fleet"
    INSTANCE = "instance"
    RUN = "run"
    JOB = "job"


class EventTarget(CoreModel):
    type: Annotated[
        str,  # not using EventTargetType to allow adding new types without breaking compatibility
        Field(
            description=(
                f"Type of the target entity."
                f" One of: {list_enum_values_for_annotation(EventTargetType)}"
            )
        ),
    ]
    project_id: Annotated[
        Optional[uuid.UUID],
        Field(
            description=(
                "ID of the project the target entity belongs to,"
                " or `null` for target types not bound to a project (e.g., users)"
            )
        ),
    ]
    project_name: Annotated[
        Optional[str],
        Field(
            description=(
                "Name of the project the target entity belongs to,"
                " or `null` for target types not bound to a project (e.g., users)"
            )
        ),
    ]
    is_project_deleted: Annotated[
        Optional[bool],
        Field(
            description=(
                "Whether the project the target entity belongs to is deleted,"
                " or `null` for target types not bound to a project (e.g., users)"
            )
        ),
    ] = None  # default for client compatibility with pre-0.20.1 servers
    id: Annotated[uuid.UUID, Field(description="ID of the target entity")]
    name: Annotated[str, Field(description="Name of the target entity")]


class Event(CoreModel):
    id: uuid.UUID
    message: str
    recorded_at: datetime
    actor_user_id: Annotated[
        Optional[uuid.UUID],
        Field(
            description=(
                "ID of the user who performed the action that triggered the event,"
                " or `null` if the action was performed by the system"
            )
        ),
    ]
    actor_user: Annotated[
        Optional[str],
        Field(
            description=(
                "Name of the user who performed the action that triggered the event,"
                " or `null` if the action was performed by the system"
            )
        ),
    ]
    is_actor_user_deleted: Annotated[
        Optional[bool],
        Field(
            description=(
                "Whether the user who performed the action that triggered the event is deleted,"
                " or `null` if the action was performed by the system"
            )
        ),
    ] = None  # default for client compatibility with pre-0.20.1 servers
    targets: Annotated[
        list[EventTarget], Field(description="List of entities affected by the event")
    ]
