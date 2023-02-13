from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer

from dstack.hub.db.models import Hub as HubDB
from dstack.hub.models import Hub, HubInfo
from dstack.hub.repository.hub import HubManager
from dstack.hub.routers.util import get_hub
from dstack.hub.security.scope import Scope

router = APIRouter(prefix="/api/hub", tags=["hub"])

security = HTTPBearer()


@router.get("", dependencies=[Depends(Scope("hub:list:read"))], response_model=List[HubInfo])
async def list_hub() -> List[HubInfo]:
    return await HubManager.list_info()


@router.post("{hub_name}/delete", dependencies=[Depends(Scope("hub:list:write"))])
async def delete_hub(hub_name: str):
    hub = await get_hub(hub_name=hub_name)
    await HubManager.remove(hub)


@router.post("/add", dependencies=[Depends(Scope("hub:add:write"))])
async def add_hub(hub: Hub):
    await HubManager.save(HubDB(name=hub.name, backend=hub.backend, config=hub.config))


@router.get("{hub_name}/info", dependencies=[Depends(Scope("hub:list:read"))])
async def info_hub(hub_name: str) -> HubInfo:
    hub = await HubManager.get_info(name=hub_name)
    if hub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hub not found",
        )
    return hub
