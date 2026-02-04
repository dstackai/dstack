import time
import uuid
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Optional

from rich.text import Text

from dstack._internal.cli.utils.common import LIVE_TABLE_PROVISION_INTERVAL_SECS, console
from dstack._internal.core.models.events import Event, EventTargetType
from dstack._internal.server.schemas.events import LIST_EVENTS_DEFAULT_LIMIT
from dstack.api.server._events import EventsAPIClient


@dataclass
class EventListFilters:
    target_fleets: Optional[list[uuid.UUID]] = None
    target_runs: Optional[list[uuid.UUID]] = None
    target_volumes: Optional[list[uuid.UUID]] = None
    target_gateways: Optional[list[uuid.UUID]] = None
    target_secrets: Optional[list[uuid.UUID]] = None
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


class EventTracker:
    """
    Tracks new events from the server. Implements a sliding window mechanism to avoid
    missing events that are commited with a delay.
    """

    def __init__(
        self,
        client: EventsAPIClient,
        filters: EventListFilters,
        since: Optional[datetime],
        event_delay_tolerance: timedelta = timedelta(seconds=20),
    ) -> None:
        self._client = client
        self._filters = filters
        self._since = since
        self._event_delay_tolerance = event_delay_tolerance
        self._seen_events: dict[uuid.UUID, _SeenEvent] = {}
        self._latest_event: Optional[Event] = None

    def poll(self) -> Iterator[Event]:
        """
        Fetches the next batch of events from the server.
        """

        if self._since is None and self._latest_event is None:
            # First batch without `since` - fetch some recent events
            event_stream = reversed(self._client.list(ascending=False, **asdict(self._filters)))
        else:
            configured_since = self._since or datetime.fromtimestamp(0)
            latest_event_recorded_at = (
                self._latest_event.recorded_at
                if self._latest_event is not None
                else datetime.fromtimestamp(0)
            )
            since = max(
                configured_since.astimezone(),
                latest_event_recorded_at.astimezone() - self._event_delay_tolerance,
            )
            self._cleanup_seen_events(before=since)
            event_stream = EventPaginator(self._client).list(self._filters, since, ascending=True)

        for event in event_stream:
            if event.id not in self._seen_events:
                self._seen_events[event.id] = _SeenEvent(recorded_at=event.recorded_at)
                yield event
            self._latest_event = event

    def stream_forever(
        self,
        update_interval: timedelta = timedelta(seconds=LIVE_TABLE_PROVISION_INTERVAL_SECS),
    ) -> Iterator[Event]:
        """
        Yields events as they are received from the server.
        """

        while True:
            for event in self.poll():
                yield event
            time.sleep(update_interval.total_seconds())

    def _cleanup_seen_events(self, before: datetime) -> None:
        ids_to_delete = {
            event_id
            for event_id, seen_event in self._seen_events.items()
            if seen_event.recorded_at.astimezone() < before.astimezone()
        }
        for event_id in ids_to_delete:
            del self._seen_events[event_id]


@dataclass
class _SeenEvent:
    recorded_at: datetime


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
