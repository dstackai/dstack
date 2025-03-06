import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, lazyload

from dstack._internal.core.errors import BackendError, BackendNotAvailable, SSHError
from dstack._internal.core.models.gateways import GatewayStatus
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import GatewayComputeModel, GatewayModel, ProjectModel
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services import gateways as gateways_services
from dstack._internal.server.services.gateways import (
    GatewayConnection,
    create_gateway_compute,
    gateway_connections_pool,
)
from dstack._internal.server.services.locking import advisory_lock_ctx, get_locker
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def process_gateways_connections():
    await _remove_inactive_connections()
    await _process_active_connections()


async def process_submitted_gateways():
    lock, lockset = get_locker().get_lockset(GatewayModel.__tablename__)
    async with get_session_ctx() as session:
        async with lock:
            res = await session.execute(
                select(GatewayModel)
                .where(
                    GatewayModel.status == GatewayStatus.SUBMITTED,
                    GatewayModel.id.not_in(lockset),
                )
                .options(lazyload(GatewayModel.gateway_compute))
                .order_by(GatewayModel.last_processed_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            gateway_model = res.scalar()
            if gateway_model is None:
                return
            lockset.add(gateway_model.id)
        try:
            gateway_model_id = gateway_model.id
            await _process_submitted_gateway(session=session, gateway_model=gateway_model)
        finally:
            lockset.difference_update([gateway_model_id])


async def _remove_inactive_connections():
    async with get_session_ctx() as session:
        res = await session.execute(
            select(GatewayComputeModel.ip_address).where(GatewayComputeModel.active == True)
        )
    active_connection_ips = set(res.scalars().all())
    for conn in await gateway_connections_pool.all():
        if conn.ip_address not in active_connection_ips:
            await gateway_connections_pool.remove(conn.ip_address)


async def _process_active_connections():
    connections = await gateway_connections_pool.all()
    # Two server processes on a single host cannot process
    # gateway connections and init gateway connections concurrently:
    # Race conditions cause conflicting tunnels being opened.
    async with get_session_ctx() as session:
        async with advisory_lock_ctx(
            bind=session,
            dialect_name=get_db().dialect_name,
            resource="gateway_tunnels",
        ):
            await asyncio.gather(*(_process_connection(conn) for conn in connections))


async def _process_connection(conn: GatewayConnection):
    try:
        await conn.check_or_restart()
    except SSHError as e:
        logger.error("Connection to gateway %s failed: %s", conn.ip_address, e)
        return

    await conn.try_collect_stats()


async def _process_submitted_gateway(session: AsyncSession, gateway_model: GatewayModel):
    logger.info("Started gateway %s provisioning", gateway_model.name)
    # Refetch to load related attributes.
    # joinedload produces LEFT OUTER JOIN that can't be used with FOR UPDATE.
    res = await session.execute(
        select(GatewayModel)
        .where(GatewayModel.id == gateway_model.id)
        .options(joinedload(GatewayModel.project).joinedload(ProjectModel.backends))
        .execution_options(populate_existing=True)
    )
    gateway_model = res.unique().scalar_one()
    configuration = gateways_services.get_gateway_configuration(gateway_model)
    try:
        (
            backend_model,
            backend,
        ) = await backends_services.get_project_backend_with_model_by_type_or_error(
            project=gateway_model.project, backend_type=configuration.backend
        )
    except BackendNotAvailable:
        gateway_model.status = GatewayStatus.FAILED
        gateway_model.status_message = "Backend not available"
        gateway_model.last_processed_at = get_current_datetime()
        await session.commit()
        return

    try:
        gateway_model.gateway_compute = await create_gateway_compute(
            backend_compute=backend.compute(),
            project_name=gateway_model.project.name,
            configuration=configuration,
            backend_id=backend_model.id,
        )
        session.add(gateway_model)
        gateway_model.status = GatewayStatus.PROVISIONING
        await session.commit()
        await session.refresh(gateway_model)
    except BackendError as e:
        logger.info(
            "Failed to create gateway compute for gateway %s: %s", gateway_model.name, repr(e)
        )
        gateway_model.status = GatewayStatus.FAILED
        status_message = f"Backend error: {repr(e)}"
        if len(e.args) > 0:
            status_message = str(e.args[0])
        gateway_model.status_message = status_message
        gateway_model.last_processed_at = get_current_datetime()
        await session.commit()
        return
    except Exception as e:
        logger.exception(
            "Got exception when creating gateway compute for gateway %s", gateway_model.name
        )
        gateway_model.status = GatewayStatus.FAILED
        gateway_model.status_message = f"Unexpected error: {repr(e)}"
        gateway_model.last_processed_at = get_current_datetime()
        await session.commit()
        return

    connection = await gateways_services.connect_to_gateway_with_retry(
        gateway_model.gateway_compute
    )
    if connection is None:
        gateway_model.status = GatewayStatus.FAILED
        gateway_model.status_message = "Failed to connect to gateway"
        gateway_model.last_processed_at = get_current_datetime()
        gateway_model.gateway_compute.deleted = True
        await session.commit()
        return

    try:
        await gateways_services.configure_gateway(connection)
    except Exception:
        logger.exception("Failed to configure gateway %s", gateway_model.name)
        gateway_model.status = GatewayStatus.FAILED
        gateway_model.status_message = "Failed to configure gateway"
        gateway_model.last_processed_at = get_current_datetime()
        await gateway_connections_pool.remove(gateway_model.gateway_compute.ip_address)
        gateway_model.gateway_compute.active = False
        await session.commit()
        return

    gateway_model.status = GatewayStatus.RUNNING
    gateway_model.last_processed_at = get_current_datetime()
    await session.commit()
