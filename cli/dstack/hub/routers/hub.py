from typing import List, Union

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPBearer

from dstack.api.backend import dict_backends
from dstack.hub.db.models import Hub as HubDB
from dstack.hub.models import AWSAuth, AWSBackend, AWSConfig, Hub, HubDelete, HubInfo
from dstack.hub.repository.hub import HubManager
from dstack.hub.routers.util import get_hub
from dstack.hub.security.scope import Scope

router = APIRouter(prefix="/api/hubs", tags=["hub"])

security = HTTPBearer()


@router.post("/backends/values")
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
    return configurator.configure_hub(request_args)


@router.post("", dependencies=[Depends(Scope("hub:list:read"))], response_model=List[HubInfo])
async def hub_create(body: HubInfo) -> HubInfo:
    hub = await HubManager.get(name=body.name)
    if hub is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Hub is exists")
    await HubManager.save(hub)
    return hub


@router.delete("", dependencies=[Depends(Scope("hub:list:write"))])
async def delete_hub(body: HubDelete):
    for hub_name in body.hub_names:
        hub = await get_hub(hub_name=hub_name)
        await HubManager.remove(hub)


@router.get("/list", dependencies=[Depends(Scope("hub:list:read"))], response_model=List[HubInfo])
async def list_hub() -> List[HubInfo]:
    return await HubManager.list_info()


@router.post("/add", dependencies=[Depends(Scope("hub:add:write"))])
async def add_hub(hub: Hub):
    await HubManager.save(HubDB(name=hub.name, backend=hub.backend, config=hub.config))


@router.get("/{hub_name}", dependencies=[Depends(Scope("hub:list:read"))])
async def info_hub(hub_name: str) -> HubInfo:
    hub = await HubManager.get_info(name=hub_name)
    if hub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hub not found",
        )
    return hub


@router.patch("/{hub_name}", dependencies=[Depends(Scope("hub:patch:write"))])
async def info_hub(hub_name: str, payload: dict = Body()) -> HubInfo:
    hub = await HubManager.get(name=hub_name)
    if hub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hub not found",
        )
    if payload.get("backend") is not None and payload.get("backend").get("type") == "aws":
        if payload.get("backend").get("s3_bucket_name") is not None:
            bucket = payload.get("backend").get("s3_bucket_name").replace("s3://", "")
            payload["backend"]["s3_bucket_name"] = bucket
        hub.auth = AWSAuth().parse_obj(payload.get("backend")).json()
        hub.config = AWSConfig().parse_obj(payload.get("backend")).json()
    await HubManager.save(hub)
    return await HubManager.get_info(name=hub_name)
