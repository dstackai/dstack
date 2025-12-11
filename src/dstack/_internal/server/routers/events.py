from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.server.services.events as events_services
from dstack._internal.core.models.events import Event
from dstack._internal.server.db import get_session
from dstack._internal.server.models import UserModel
from dstack._internal.server.schemas.events import ListEventsRequest
from dstack._internal.server.security.permissions import Authenticated
from dstack._internal.server.utils.routers import (
    CustomORJSONResponse,
    get_base_api_additional_responses,
)

root_router = APIRouter(
    prefix="/api/events",
    tags=["events"],
    responses=get_base_api_additional_responses(),
)


@root_router.post("/list", response_model=list[Event])
async def list_events(
    body: ListEventsRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(Authenticated()),
):
    """
    Returns events visible to the current user.

    Regular users can see events related to themselves and to projects they are members of.
    Global admins can see all events.

    The results are paginated. To get the next page, pass `recorded_at` and `id` of
    the last event from the previous page as `prev_recorded_at` and `prev_id`.
    """
    return CustomORJSONResponse(
        await events_services.list_events(
            session=session,
            user=user,
            target_projects=body.target_projects,
            target_users=body.target_users,
            target_fleets=body.target_fleets,
            target_instances=body.target_instances,
            target_runs=body.target_runs,
            target_jobs=body.target_jobs,
            within_projects=body.within_projects,
            within_fleets=body.within_fleets,
            within_runs=body.within_runs,
            include_target_types=body.include_target_types,
            actors=body.actors,
            prev_recorded_at=body.prev_recorded_at,
            prev_id=body.prev_id,
            limit=body.limit,
            ascending=body.ascending,
        )
    )
