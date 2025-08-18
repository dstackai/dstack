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
from dstack._internal.server.services.logging import fmt
from dstack._internal.server.utils import sentry_utils
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def process_gateways_connections():
    await _remove_inactive_connections()
    await _process_active_connections()


@sentry_utils.instrument_background_task
async def process_gateways():
    lock, lockset = get_locker(get_db().dialect_name).get_lockset(GatewayModel.__tablename__)
    async with get_session_ctx() as session:
        async with lock:
            res = await session.execute(
                select(GatewayModel)
                .where(
                    GatewayModel.status.in_([GatewayStatus.SUBMITTED, GatewayStatus.PROVISIONING]),
                    GatewayModel.id.not_in(lockset),
                )
                .options(lazyload(GatewayModel.gateway_compute))
                .order_by(GatewayModel.last_processed_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True, key_share=True)
            )
            gateway_model = res.scalar()
            if gateway_model is None:
                return
            lockset.add(gateway_model.id)
        gateway_model_id = gateway_model.id
        try:
            initial_status = gateway_model.status
            if initial_status == GatewayStatus.SUBMITTED:
                await _process_submitted_gateway(session=session, gateway_model=gateway_model)
            elif initial_status == GatewayStatus.PROVISIONING:
                await _process_provisioning_gateway(session=session, gateway_model=gateway_model)
            else:
                logger.error(
                    "%s: unexpected gateway status %r", fmt(gateway_model), initial_status.upper()
                )
            if gateway_model.status != initial_status:
                logger.info(
                    "%s: gateway status has changed %s -> %s%s",
                    fmt(gateway_model),
                    initial_status.upper(),
                    gateway_model.status.upper(),
                    f": {gateway_model.status_message}" if gateway_model.status_message else "",
                )
            gateway_model.last_processed_at = get_current_datetime()
            await session.commit()
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
    logger.info("%s: started gateway provisioning", fmt(gateway_model))
    # Refetch to load related attributes.
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
    except BackendError as e:
        logger.info("%s: failed to create gateway compute: %r", fmt(gateway_model), e)
        gateway_model.status = GatewayStatus.FAILED
        status_message = f"Backend error: {repr(e)}"
        if len(e.args) > 0:
            status_message = str(e.args[0])
        gateway_model.status_message = status_message
    except Exception as e:
        logger.exception("%s: got exception when creating gateway compute", fmt(gateway_model))
        gateway_model.status = GatewayStatus.FAILED
        gateway_model.status_message = f"Unexpected error: {repr(e)}"


async def _process_provisioning_gateway(
    session: AsyncSession, gateway_model: GatewayModel
) -> None:
    # Refetch to load related attributes.
    res = await session.execute(
        select(GatewayModel)
        .where(GatewayModel.id == gateway_model.id)
        .execution_options(populate_existing=True)
    )
    gateway_model = res.unique().scalar_one()

    # Provisioning gateways must have compute.
    assert gateway_model.gateway_compute is not None

    # FIXME: problems caused by blocking on connect_to_gateway_with_retry and configure_gateway:
    # - cannot delete the gateway before it is provisioned because the DB model is locked
    # - connection retry counter is reset on server restart
    # - only one server replica is processing the gateway
    # Easy to fix by doing only one connection/configuration attempt per processing iteration. The
    # main challenge is applying the same provisioning model to the dstack Sky gateway to avoid
    # maintaining a different model for Sky.
    connection = await gateways_services.connect_to_gateway_with_retry(
        gateway_model.gateway_compute
    )
    if connection is None:
        gateway_model.status = GatewayStatus.FAILED
        gateway_model.status_message = "Failed to connect to gateway"
        gateway_model.gateway_compute.deleted = True
        return
    try:
        await gateways_services.configure_gateway(connection)
    except Exception:
        logger.exception("%s: failed to configure gateway", fmt(gateway_model))
        gateway_model.status = GatewayStatus.FAILED
        gateway_model.status_message = "Failed to configure gateway"
        await gateway_connections_pool.remove(gateway_model.gateway_compute.ip_address)
        gateway_model.gateway_compute.active = False
        return

    gateway_model.status = GatewayStatus.RUNNING
