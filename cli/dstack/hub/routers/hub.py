from typing import List

from fastapi import APIRouter, Depends, Security
from fastapi.security import HTTPBearer


from dstack.hub.security.scope import Scope
from dstack.hub.models import Hub

router = APIRouter(prefix="/api/hub", tags=["hub"])

security = HTTPBearer()


@router.get("", dependencies=[Depends(Scope("hub:list:read"))])
async def list_hub() -> List[str]:
    return ["1", "2"]
@router.get("/delete", dependencies=[Depends(Scope("hub:list:read"))])
async def delete_hub() -> List[str]:
    return ["1", "2"]


@router.post("/add", dependencies=[Depends(Scope("hub:add:write"))])
async def add_hub(hub: Hub):
    pass
