from fastapi import HTTPException, status

from dstack.hub.models import Hub
from dstack.hub.repository.hub import HubManager


async def get_hub(hub_name: str) -> Hub:
    hub = await HubManager.get(name=hub_name)
    if hub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hub not found",
        )
    return hub
