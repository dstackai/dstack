import asyncio
from typing import List, Optional, Tuple

from dstack._internal.backend.base import Backend
from dstack._internal.core.instance import InstanceOffer
from dstack._internal.core.job import Job
from dstack._internal.hub.db.models import Backend as DBBackend
from dstack._internal.hub.db.models import Project
from dstack._internal.hub.services.backends import cache as backends_cache
from dstack._internal.hub.utils.common import run_async


async def get_backends(
    project: Project, selected_backends: Optional[List[str]] = None
) -> List[Tuple[DBBackend, Backend]]:
    backends = await backends_cache.get_project_backends(project)
    if not selected_backends:
        return backends
    return [
        (db_backend, backend)
        for db_backend, backend in backends
        if db_backend.type in selected_backends
    ]


async def get_instance_candidates(
    backends: List[Backend], job: Job
) -> List[Tuple[Backend, InstanceOffer]]:
    """
    Returns list of instances satisfying minimal resource requirements sorted by price
    """
    candidates = []
    tasks = [
        run_async(backend.get_instance_candidates, job.requirements, job.spot_policy)
        for backend in backends
    ]
    for backend, backend_candidates in zip(backends, await asyncio.gather(*tasks)):
        for instance in backend_candidates:
            candidates.append((backend, instance))
    return sorted(candidates, key=lambda x: x[1].price)
