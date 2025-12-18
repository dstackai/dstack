import uuid
from datetime import datetime
from typing import Annotated, Optional
from uuid import UUID

from pydantic import Field, root_validator

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.events import EventTargetType

MIN_FILTER_ITEMS = 1
MAX_FILTER_ITEMS = 16  # Conservative limit to prevent overly complex db queries
LIST_EVENTS_DEFAULT_LIMIT = 100


class ListEventsRequest(CoreModel):
    target_projects: Annotated[
        Optional[list[uuid.UUID]],
        Field(
            description=(
                "List of project IDs."
                " The response will only include events that target the specified projects"
            ),
            min_items=MIN_FILTER_ITEMS,
            max_items=MAX_FILTER_ITEMS,
        ),
    ] = None
    target_users: Annotated[
        Optional[list[uuid.UUID]],
        Field(
            description=(
                "List of user IDs."
                " The response will only include events that target the specified users"
            ),
            min_items=MIN_FILTER_ITEMS,
            max_items=MAX_FILTER_ITEMS,
        ),
    ] = None
    target_fleets: Annotated[
        Optional[list[uuid.UUID]],
        Field(
            description=(
                "List of fleet IDs."
                " The response will only include events that target the specified fleets"
            ),
            min_items=MIN_FILTER_ITEMS,
            max_items=MAX_FILTER_ITEMS,
        ),
    ] = None
    target_instances: Annotated[
        Optional[list[uuid.UUID]],
        Field(
            description=(
                "List of instance IDs."
                " The response will only include events that target the specified instances"
            ),
            min_items=MIN_FILTER_ITEMS,
            max_items=MAX_FILTER_ITEMS,
        ),
    ] = None
    target_runs: Annotated[
        Optional[list[uuid.UUID]],
        Field(
            description=(
                "List of run IDs."
                " The response will only include events that target the specified runs"
            ),
            min_items=MIN_FILTER_ITEMS,
            max_items=MAX_FILTER_ITEMS,
        ),
    ] = None
    target_jobs: Annotated[
        Optional[list[uuid.UUID]],
        Field(
            description=(
                "List of job IDs."
                " The response will only include events that target the specified jobs"
            ),
            min_items=MIN_FILTER_ITEMS,
            max_items=MAX_FILTER_ITEMS,
        ),
    ] = None
    within_projects: Annotated[
        Optional[list[uuid.UUID]],
        Field(
            description=(
                "List of project IDs."
                " The response will only include events that target the specified projects"
                " or any entities within those projects"
            ),
            min_items=MIN_FILTER_ITEMS,
            max_items=MAX_FILTER_ITEMS,
        ),
    ] = None
    within_fleets: Annotated[
        Optional[list[uuid.UUID]],
        Field(
            description=(
                "List of fleet IDs."
                " The response will only include events that target the specified fleets"
                " or instances within those fleets"
            ),
            min_items=MIN_FILTER_ITEMS,
            max_items=MAX_FILTER_ITEMS,
        ),
    ] = None
    within_runs: Annotated[
        Optional[list[uuid.UUID]],
        Field(
            description=(
                "List of run IDs."
                " The response will only include events that target the specified runs"
                " or jobs within those runs"
            ),
            min_items=MIN_FILTER_ITEMS,
            max_items=MAX_FILTER_ITEMS,
        ),
    ] = None
    include_target_types: Annotated[
        Optional[list[EventTargetType]],
        Field(
            description=(
                "List of target types."
                " The response will only include events that have a target"
                " of one of the specified types"
            ),
            min_items=MIN_FILTER_ITEMS,
            max_items=MAX_FILTER_ITEMS,
        ),
    ] = None
    actors: Annotated[
        Optional[list[Optional[uuid.UUID]]],
        Field(
            description=(
                "List of user IDs or `null` values."
                " The response will only include events about actions"
                " performed by the specified users,"
                " or performed by the system if `null` is specified"
            ),
            min_items=MIN_FILTER_ITEMS,
            max_items=MAX_FILTER_ITEMS,
        ),
    ] = None
    prev_recorded_at: Optional[datetime] = None
    prev_id: Optional[UUID] = None
    limit: int = Field(LIST_EVENTS_DEFAULT_LIMIT, ge=1, le=100)
    ascending: bool = False

    @root_validator
    def _validate_target_filters(cls, values):
        """
        Raise an error if more than one target_* filter is set. Setting multiple
        target_* filters would always result in an empty response, which might confuse users.
        """

        target_filters = [name for name in cls.__fields__ if name.startswith("target_")]
        set_filters = [f for f in target_filters if values.get(f) is not None]
        if len(set_filters) > 1:
            raise ValueError(
                f"At most one target_* filter can be set at a time. Got {', '.join(set_filters)}"
            )
        return values

    @root_validator
    def _validate_within_filters(cls, values):
        """
        Raise an error if more than one within_* filter is set. Setting multiple
        within_* filters is either redundant or incorrect. Each within_* filter
        may also lead to additional db queries, causing unnecessary load.
        """

        within_filters = [name for name in cls.__fields__ if name.startswith("within_")]
        set_filters = [f for f in within_filters if values.get(f) is not None]
        if len(set_filters) > 1:
            raise ValueError(
                f"At most one within_* filter can be set at a time. Got {', '.join(set_filters)}"
            )
        return values
