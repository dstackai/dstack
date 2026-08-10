from typing import Annotated

from fastapi import APIRouter, Depends

from dstack._internal.proxy.gateway.deps import get_gateway_proxy_repo
from dstack._internal.proxy.gateway.repo.repo import GatewayProxyRepo
from dstack._internal.proxy.gateway.schemas.services import ServiceListResponse
from dstack._internal.proxy.gateway.services.services import list_services

router = APIRouter()


@router.get("/list")
async def list_all_services(
    repo: Annotated[GatewayProxyRepo, Depends(get_gateway_proxy_repo)],
) -> ServiceListResponse:
    return await list_services(repo)
