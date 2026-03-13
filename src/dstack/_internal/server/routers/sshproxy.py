import os
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import ResourceNotExistsError
from dstack._internal.server.db import get_session
from dstack._internal.server.schemas.sshproxy import GetUpstreamRequest, GetUpstreamResponse
from dstack._internal.server.security.permissions import AlwaysForbidden, ServiceAccount
from dstack._internal.server.services.sshproxy import get_upstream_response
from dstack._internal.server.utils.routers import (
    CustomORJSONResponse,
    get_base_api_additional_responses,
)

if _token := os.getenv("DSTACK_SSHPROXY_API_TOKEN"):
    _auth = ServiceAccount(_token)
else:
    _auth = AlwaysForbidden()


router = APIRouter(
    prefix="/api/sshproxy",
    tags=["sshproxy"],
    responses=get_base_api_additional_responses(),
    dependencies=[Depends(_auth)],
)


@router.post("/get_upstream", response_model=GetUpstreamResponse)
async def get_upstream(
    body: GetUpstreamRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    response = await get_upstream_response(session=session, upstream_id=body.id)
    if response is None:
        raise ResourceNotExistsError()
    return CustomORJSONResponse(response)
