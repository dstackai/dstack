from typing import Dict

from fastapi import APIRouter, Depends

from dstack.gateway.stats.collector import StatsCollector, get_collector
from dstack.gateway.stats.schemas import Stat

router = APIRouter()


@router.get("/collect")
async def get_collect_stats(
    collector: StatsCollector = Depends(get_collector),
) -> Dict[str, Dict[int, Stat]]:
    return await collector.collect()
