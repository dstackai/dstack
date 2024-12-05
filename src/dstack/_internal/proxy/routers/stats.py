from typing import Annotated

from fastapi import APIRouter, Depends

from dstack._internal.proxy.deps import get_proxy_repo, get_stats_collector
from dstack._internal.proxy.repos.memory import InMemoryProxyRepo
from dstack._internal.proxy.schemas.stats import ServiceStats
from dstack._internal.proxy.services.stats import StatsCollector, get_service_stats

router = APIRouter()


@router.get("/collect")
async def collect_stats(
    repo: Annotated[
        InMemoryProxyRepo, Depends(get_proxy_repo)
    ],  # TODO: safe dependency on GatewayRepo
    collector: Annotated[StatsCollector, Depends(get_stats_collector)],
) -> list[ServiceStats]:
    return await get_service_stats(repo, collector)
