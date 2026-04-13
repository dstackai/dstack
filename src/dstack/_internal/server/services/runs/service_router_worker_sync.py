"""Service-router replica pipeline: detect router groups and ensure sync table rows."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.utils.common as common_utils
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.runs import RunSpec
from dstack._internal.server.models import RunModel, ServiceRouterWorkerSyncModel


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
            sync_row.deleted = False
            sync_row.lock_expires_at = None
            sync_row.lock_token = None
            sync_row.lock_owner = None
            sync_row.last_processed_at = now
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
