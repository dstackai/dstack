"""Service-router replica pipeline: detect router groups and ensure sync table rows."""

import uuid
from datetime import datetime
from typing import Optional, TypedDict

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.utils.common as common_utils
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.runs import RunSpec
from dstack._internal.server.models import RunModel, ServiceRouterWorkerSyncModel


class _SyncRowUpdateMap(TypedDict, total=False):
    deleted: bool
    last_processed_at: datetime
    lock_expires_at: Optional[datetime]
    lock_token: Optional[uuid.UUID]
    lock_owner: Optional[str]


def _reactivate_sync_row_update_map(*, now: datetime) -> _SyncRowUpdateMap:
    return {
        "deleted": False,
        "last_processed_at": now,
        "lock_expires_at": None,
        "lock_token": None,
        "lock_owner": None,
    }


def run_spec_has_router_replica_group(run_spec: RunSpec) -> bool:
    if run_spec.configuration.type != "service":
        return False
    cfg = run_spec.configuration
    if not isinstance(cfg, ServiceConfiguration):
        return False
    return any(g.router is not None for g in cfg.replica_groups)


async def ensure_service_router_worker_sync_row(
    session: AsyncSession,
    run_model: RunModel,
    run_spec: RunSpec,
) -> None:
    if not run_spec_has_router_replica_group(run_spec):
        return
    res = await session.execute(
        select(ServiceRouterWorkerSyncModel).where(
            ServiceRouterWorkerSyncModel.run_id == run_model.id
        )
    )
    sync_row = res.scalar_one_or_none()
    now = common_utils.get_current_datetime()
    if sync_row is not None:
        if sync_row.deleted:
            # If the router replica group is reintroduced in service configuration (via re-apply),
            # reactivate the existing sync row so the background pipeline resumes syncing router workers.
            update_map = _reactivate_sync_row_update_map(now=now)
            await session.execute(
                update(ServiceRouterWorkerSyncModel)
                .where(ServiceRouterWorkerSyncModel.id == sync_row.id)
                .values(**update_map)
            )
        return
    session.add(
        ServiceRouterWorkerSyncModel(
            id=uuid.uuid4(),
            run_id=run_model.id,
            deleted=False,
            created_at=now,
            last_processed_at=now,
        )
    )
