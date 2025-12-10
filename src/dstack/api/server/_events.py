from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from pydantic import parse_obj_as

from dstack._internal.core.models.events import Event, EventTargetType
from dstack._internal.server.schemas.events import LIST_EVENTS_DEFAULT_LIMIT, ListEventsRequest
from dstack.api.server._group import APIClientGroup


class EventsAPIClient(APIClientGroup):
    def list(
        self,
        target_projects: Optional[list[UUID]] = None,
        target_users: Optional[list[UUID]] = None,
        target_fleets: Optional[list[UUID]] = None,
        target_instances: Optional[list[UUID]] = None,
        target_runs: Optional[list[UUID]] = None,
        target_jobs: Optional[list[UUID]] = None,
        within_projects: Optional[list[UUID]] = None,
        within_fleets: Optional[list[UUID]] = None,
        within_runs: Optional[list[UUID]] = None,
        include_target_types: Optional[list[EventTargetType]] = None,
        actors: Optional[list[Optional[UUID]]] = None,
        prev_recorded_at: Optional[datetime] = None,
        prev_id: Optional[UUID] = None,
        limit: int = LIST_EVENTS_DEFAULT_LIMIT,
        ascending: bool = False,
    ) -> list[Event]:
        if prev_recorded_at is not None:
            # Time zones other than UTC are misinterpreted by the server:
            # https://github.com/dstackai/dstack/issues/3354
            prev_recorded_at = prev_recorded_at.astimezone(timezone.utc)
        req = ListEventsRequest(
            target_projects=target_projects,
            target_users=target_users,
            target_fleets=target_fleets,
            target_instances=target_instances,
            target_runs=target_runs,
            target_jobs=target_jobs,
            within_projects=within_projects,
            within_fleets=within_fleets,
            within_runs=within_runs,
            include_target_types=include_target_types,
            actors=actors,
            prev_recorded_at=prev_recorded_at,
            prev_id=prev_id,
            limit=limit,
            ascending=ascending,
        )
        resp = self._request("/api/events/list", body=req.json())
        return parse_obj_as(list[Event.__response__], resp.json())
