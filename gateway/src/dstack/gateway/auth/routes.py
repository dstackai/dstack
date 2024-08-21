from fastapi import APIRouter, Depends

from dstack.gateway.core.auth import access_to_project_required

router = APIRouter()


# TODO(egor-s): support Authorization header alternative for web browsers


@router.get("/{project}", dependencies=[Depends(access_to_project_required)])
async def get_auth():
    return {"status": "ok"}
