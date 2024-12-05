from typing import Dict

from fastapi import APIRouter

from dstack._internal.proxy.schemas.stats import Stat

router = APIRouter()


@router.get("/collect")
async def get_collect_stats() -> Dict[str, Dict[int, Stat]]:
    # TODO
    return {}
