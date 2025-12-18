import uuid
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Optional

from rich.text import Text

from dstack._internal.cli.utils.common import console
from dstack._internal.core.models.events import Event, EventTargetType
from dstack._internal.server.schemas.events import LIST_EVENTS_DEFAULT_LIMIT
from dstack.api.server._events import EventsAPIClient


@dataclass
class EventListFilters:
    target_fleets: Optional[list[uuid.UUID]] = None
    target_runs: Optional[list[uuid.UUID]] = None
    within_projects: Optional[list[uuid.UUID]] = None
    within_fleets: Optional[list[uuid.UUID]] = None
    within_runs: Optional[list[uuid.UUID]] = None
    include_target_types: Optional[list[EventTargetType]] = None


class EventPaginator:
    def __init__(self, client: EventsAPIClient) -> None:
        self._client = client

    def list(
        self, filters: EventListFilters, since: Optional[datetime], ascending: bool
    ) -> Iterator[Event]:
        prev_id = None
        prev_recorded_at = since
        while True:
            events = self._client.list(
                prev_id=prev_id,
                prev_recorded_at=prev_recorded_at,
                limit=LIST_EVENTS_DEFAULT_LIMIT,
                ascending=ascending,
                **asdict(filters),
            )
            for event in events:
                yield event
            if len(events) < LIST_EVENTS_DEFAULT_LIMIT:
                break
            prev_id = events[-1].id
            prev_recorded_at = events[-1].recorded_at


def print_event(event: Event) -> None:
    recorded_at = event.recorded_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    targets = ", ".join(f"{target.type} {target.name}" for target in event.targets)
    message = [
        Text(f"[{recorded_at}]", style="log.time"),
    ]
    if event.actor_user:
        message.append(Text(f"[👤{event.actor_user}]", style="secondary"))
    message += [
        Text(f"[{targets}]", style="secondary"),
        Text(event.message, style="log.message"),
    ]
    console.print(
        *message,
        soft_wrap=True,  # Strictly one line per event. Allows for grepping
    )
