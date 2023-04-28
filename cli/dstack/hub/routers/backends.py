from typing import List

from fastapi import APIRouter, Depends

from dstack.hub.models import BackendType
from dstack.hub.security.permissions import Authenticated
from dstack.hub.services.backends import list_avaialble_backend_types

router = APIRouter(
    prefix="/api/backends", tags=["backends"], dependencies=[Depends(Authenticated())]
)


@router.post("/list")
async def list_backend_types() -> List[BackendType]:
    return list_avaialble_backend_types()
