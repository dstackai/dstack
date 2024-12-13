from fastapi import APIRouter, Depends

from dstack._internal.proxy.lib.deps import ProxyAuth

router = APIRouter()


@router.get("/{project_name}", dependencies=[Depends(ProxyAuth(auto_enforce=True))])
async def get_auth():
    return {"status": "ok"}
