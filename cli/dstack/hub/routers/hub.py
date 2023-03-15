from typing import List, Union

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPBearer

from dstack.api.backend import dict_backends
from dstack.core.error import HubError
from dstack.hub.models import AWSAuth, AWSConfig, HubDelete, HubInfo, Member
from dstack.hub.repository.hub import HubManager
from dstack.hub.routers.util import get_hub
from dstack.hub.security.scope import Scope
from dstack.hub.util import info2hub

router = APIRouter(prefix="/api/hubs", tags=["hub"])
router_project = APIRouter(prefix="/api/projects", tags=["project"])

security = HTTPBearer()


@router.post("/backends/values", deprecated=True)
@router_project.post("/backends/values")
async def backend_configurator(req: Request, type_backend: str = Query(alias="type")):
    if type_backend.lower() != "aws":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"{type_backend} not support"
        )
    backend = dict_backends(all_backend=True).get(type_backend.lower())
    if backend is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"{type_backend} not support"
        )
    request_args = dict(req.query_params)
    configurator = backend.get_configurator()
    try:
        result = configurator.configure_hub(request_args)
    except HubError as ex:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ex.message,
        )
    except Exception as exx:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return result


@router.get(
    "/list",
    dependencies=[Depends(Scope("hub:list:read"))],
    response_model=List[HubInfo],
    deprecated=True,
)
@router_project.get(
    "/list", dependencies=[Depends(Scope("hub:list:read"))], response_model=List[HubInfo]
)
async def list_hub() -> List[HubInfo]:
    return await HubManager.list_info()


@router.post(
    "", dependencies=[Depends(Scope("hub:hubs:write"))], response_model=HubInfo, deprecated=True
)
@router_project.post("", dependencies=[Depends(Scope("hub:hubs:write"))], response_model=HubInfo)
async def hub_create(body: HubInfo) -> HubInfo:
    hub = await HubManager.get(name=body.hub_name)
    if hub is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Hub is exists")
    await HubManager.save(info2hub(body))
    return body


@router.delete("", dependencies=[Depends(Scope("hub:delete:write"))], deprecated=True)
@router_project.delete("", dependencies=[Depends(Scope("hub:delete:write"))])
async def delete_hub(body: HubDelete):
    for hub_name in body.hubs:
        hub = await get_hub(hub_name=hub_name)
        await HubManager.remove(hub)


@router.post(
    "/{hub_name}/members", dependencies=[Depends(Scope("hub:members:write"))], deprecated=True
)
@router_project.post("/{hub_name}/members", dependencies=[Depends(Scope("hub:members:write"))])
async def hub_members(hub_name: str, body: List[Member] = Body()):
    hub = await get_hub(hub_name=hub_name)
    await HubManager.clear_member(hub=hub)
    for member in body:
        await HubManager.add_member(hub=hub, member=member)


@router.get("/{hub_name}", dependencies=[Depends(Scope("hub:list:read"))], deprecated=True)
@router_project.get("/{hub_name}", dependencies=[Depends(Scope("hub:list:read"))])
async def info_hub(hub_name: str) -> HubInfo:
    hub = await HubManager.get_info(name=hub_name)
    if hub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hub not found",
        )
    return hub


@router.patch("/{hub_name}", dependencies=[Depends(Scope("hub:patch:write"))], deprecated=True)
@router_project.patch("/{hub_name}", dependencies=[Depends(Scope("hub:patch:write"))])
async def patch_hub(hub_name: str, payload: dict = Body()) -> HubInfo:
    hub = await get_hub(hub_name=hub_name)
    if payload.get("backend") is not None and payload.get("backend").get("type") == "aws":
        if payload.get("backend").get("s3_bucket_name") is not None:
            bucket = payload.get("backend").get("s3_bucket_name").replace("s3://", "")
            payload["backend"]["s3_bucket_name"] = bucket
        hub.auth = AWSAuth().parse_obj(payload.get("backend")).json()
        hub.config = AWSConfig().parse_obj(payload.get("backend")).json()
    await HubManager.save(hub)
    return await HubManager.get_info(name=hub_name)
