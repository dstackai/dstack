import uuid
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from dstack._internal.core.backends.base.compute import ComputeWithVolumeSupport
from dstack._internal.core.backends.features import BACKENDS_WITH_VOLUMES_SUPPORT
from dstack._internal.core.errors import (
    BackendNotAvailable,
    ResourceExistsError,
    ServerClientError,
)
from dstack._internal.core.models.profiles import parse_duration
from dstack._internal.core.models.volumes import (
    Volume,
    VolumeAttachment,
    VolumeAttachmentData,
    VolumeConfiguration,
    VolumeInstance,
    VolumeProvisioningData,
    VolumeSpec,
    VolumeStatus,
)
from dstack._internal.core.services import validate_dstack_resource_name
from dstack._internal.server.db import get_db, is_db_postgres, is_db_sqlite
from dstack._internal.server.models import (
    InstanceModel,
    ProjectModel,
    UserModel,
    VolumeAttachmentModel,
    VolumeModel,
)
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services import events
from dstack._internal.server.services.instances import get_instance_provisioning_data
from dstack._internal.server.services.locking import (
    get_locker,
    string_to_lock_id,
)
from dstack._internal.server.services.pipelines import PipelineHinterProtocol
from dstack._internal.server.services.plugins import apply_plugin_policies
from dstack._internal.server.services.projects import list_user_project_models
from dstack._internal.settings import FeatureFlags
from dstack._internal.utils import common, random_names
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


def switch_volume_status(
    session: AsyncSession,
    volume_model: VolumeModel,
    new_status: VolumeStatus,
    actor: events.AnyActor = events.SystemActor(),
):
    old_status = volume_model.status
    if old_status == new_status:
        return

    volume_model.status = new_status
    emit_volume_status_change_event(
        session=session,
        volume_model=volume_model,
        old_status=old_status,
        new_status=new_status,
        status_message=volume_model.status_message,
        actor=actor,
    )


def emit_volume_status_change_event(
    session: AsyncSession,
    volume_model: VolumeModel,
    old_status: VolumeStatus,
    new_status: VolumeStatus,
    status_message: Optional[str],
    actor: events.AnyActor = events.SystemActor(),
) -> None:
    if old_status == new_status:
        return
    msg = get_volume_status_change_message(
        old_status=old_status,
        new_status=new_status,
        status_message=status_message,
    )
    events.emit(session, msg, actor=actor, targets=[events.Target.from_model(volume_model)])


def get_volume_status_change_message(
    old_status: VolumeStatus,
    new_status: VolumeStatus,
    status_message: Optional[str],
) -> str:
    msg = f"Volume status changed {old_status.upper()} -> {new_status.upper()}"
    if status_message is not None:
        msg += f" ({status_message})"
    return msg


async def list_volumes(
    session: AsyncSession,
    user: UserModel,
    project_name: Optional[str],
    only_active: bool,
    prev_created_at: Optional[datetime],
    prev_id: Optional[uuid.UUID],
    limit: int,
    ascending: bool,
) -> List[Volume]:
    projects = await list_user_project_models(
        session=session,
        user=user,
        only_names=True,
    )
    if project_name is not None:
        projects = [p for p in projects if p.name == project_name]
    volume_models = await list_projects_volume_models(
        session=session,
        projects=projects,
        only_active=only_active,
        prev_created_at=prev_created_at,
        prev_id=prev_id,
        limit=limit,
        ascending=ascending,
    )
    return [volume_model_to_volume(v) for v in volume_models]


async def list_projects_volume_models(
    session: AsyncSession,
    projects: List[ProjectModel],
    only_active: bool,
    prev_created_at: Optional[datetime],
    prev_id: Optional[uuid.UUID],
    limit: int,
    ascending: bool,
) -> List[VolumeModel]:
    filters = []
    filters.append(VolumeModel.project_id.in_(p.id for p in projects))
    if only_active:
        filters.append(VolumeModel.deleted == False)
    if prev_created_at is not None:
        if ascending:
            if prev_id is None:
                filters.append(VolumeModel.created_at > prev_created_at)
            else:
                filters.append(
                    or_(
                        VolumeModel.created_at > prev_created_at,
                        and_(VolumeModel.created_at == prev_created_at, VolumeModel.id < prev_id),
                    )
                )
        else:
            if prev_id is None:
                filters.append(VolumeModel.created_at < prev_created_at)
            else:
                filters.append(
                    or_(
                        VolumeModel.created_at < prev_created_at,
                        and_(VolumeModel.created_at == prev_created_at, VolumeModel.id > prev_id),
                    )
                )
    order_by = (VolumeModel.created_at.desc(), VolumeModel.id)
    if ascending:
        order_by = (VolumeModel.created_at.asc(), VolumeModel.id.desc())
    res = await session.execute(
        select(VolumeModel)
        .where(*filters)
        .order_by(*order_by)
        .limit(limit)
        .options(joinedload(VolumeModel.user))
        .options(
            joinedload(VolumeModel.attachments)
            .joinedload(VolumeAttachmentModel.instance)
            .joinedload(InstanceModel.fleet)
        )
    )
    volume_models = list(res.unique().scalars().all())
    return volume_models


async def list_project_volumes(
    session: AsyncSession,
    project: ProjectModel,
    names: Optional[List[str]] = None,
) -> List[Volume]:
    volume_models = await list_project_volume_models(session=session, project=project, names=names)
    return [volume_model_to_volume(v) for v in volume_models]


async def list_project_volume_models(
    session: AsyncSession,
    project: ProjectModel,
    names: Optional[List[str]] = None,
    include_deleted: bool = False,
) -> List[VolumeModel]:
    filters = [
        VolumeModel.project_id == project.id,
    ]
    if names is not None:
        filters.append(VolumeModel.name.in_(names))
    if not include_deleted:
        filters.append(VolumeModel.deleted == False)
    res = await session.execute(
        select(VolumeModel)
        .where(*filters)
        .options(joinedload(VolumeModel.user))
        .options(
            joinedload(VolumeModel.attachments)
            .joinedload(VolumeAttachmentModel.instance)
            .joinedload(InstanceModel.fleet)
        )
    )
    return list(res.unique().scalars().all())


async def get_volume_by_name(
    session: AsyncSession, project: ProjectModel, name: str
) -> Optional[Volume]:
    volume_model = await get_project_volume_model_by_name(
        session=session, project=project, name=name
    )
    if volume_model is None:
        return None
    return volume_model_to_volume(volume_model)


async def get_project_volume_model_by_name(
    session: AsyncSession,
    project: ProjectModel,
    name: str,
    include_deleted: bool = False,
) -> Optional[VolumeModel]:
    filters = [
        VolumeModel.name == name,
        VolumeModel.project_id == project.id,
    ]
    if not include_deleted:
        filters.append(VolumeModel.deleted == False)
    res = await session.execute(
        select(VolumeModel)
        .where(*filters)
        .options(joinedload(VolumeModel.user))
        .options(
            joinedload(VolumeModel.attachments)
            .joinedload(VolumeAttachmentModel.instance)
            .joinedload(InstanceModel.fleet)
        )
    )
    return res.unique().scalar_one_or_none()


async def create_volume(
    session: AsyncSession,
    project: ProjectModel,
    user: UserModel,
    configuration: VolumeConfiguration,
    pipeline_hinter: PipelineHinterProtocol,
) -> Volume:
    spec = await apply_plugin_policies(
        user=user.name,
        project=project.name,
        # Create pseudo spec until the volume API is updated to accept spec
        spec=VolumeSpec(configuration=configuration),
    )
    configuration = spec.configuration
    _validate_volume_configuration(configuration)

    lock_namespace = f"volume_names_{project.name}"
    if is_db_sqlite():
        # Start new transaction to see committed changes after lock
        await session.commit()
    elif is_db_postgres():
        await session.execute(
            select(func.pg_advisory_xact_lock(string_to_lock_id(lock_namespace)))
        )
    lock, _ = get_locker(get_db().dialect_name).get_lockset(lock_namespace)
    async with lock:
        if configuration.name is not None:
            volume_model = await get_project_volume_model_by_name(
                session=session,
                project=project,
                name=configuration.name,
            )
            if volume_model is not None:
                raise ResourceExistsError()
        else:
            configuration.name = await generate_volume_name(session=session, project=project)

        now = common.get_current_datetime()
        volume_model = VolumeModel(
            id=uuid.uuid4(),
            name=configuration.name,
            user_id=user.id,
            project=project,
            status=VolumeStatus.SUBMITTED,
            configuration=configuration.json(),
            auto_cleanup_enabled=_get_autocleanup_enabled(configuration),
            attachments=[],
            created_at=now,
            last_processed_at=now,
        )
        session.add(volume_model)
        events.emit(
            session,
            message=f"Volume created. Status: {volume_model.status.upper()}",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(volume_model)],
        )
        await session.commit()
        pipeline_hinter.hint_fetch(VolumeModel.__name__)
        return volume_model_to_volume(volume_model)


async def delete_volumes(
    session: AsyncSession, project: ProjectModel, names: List[str], user: UserModel
):
    # Keep both delete code paths while pipeline processing is behind a feature flag:
    # - pipeline path marks volumes for async deletion by VolumePipeline
    # - sync path deletes volume inline for non-pipeline processing
    # TODO: Drop sync path after pipeline processing is enabled by default.
    if FeatureFlags.PIPELINE_PROCESSING_ENABLED:
        await _delete_volumes_pipeline(
            session=session,
            project=project,
            names=names,
            user=user,
        )
    else:
        await _delete_volumes_sync(
            session=session,
            project=project,
            names=names,
            user=user,
        )


async def _delete_volumes_pipeline(
    session: AsyncSession, project: ProjectModel, names: List[str], user: UserModel
):
    res = await session.execute(
        select(VolumeModel).where(
            VolumeModel.project_id == project.id,
            VolumeModel.name.in_(names),
            VolumeModel.deleted == False,
        )
    )
    volume_models = res.scalars().all()
    volumes_ids = sorted([v.id for v in volume_models])
    await session.commit()
    logger.info("Deleting volumes: %s", [v.name for v in volume_models])
    async with get_locker(get_db().dialect_name).lock_ctx(VolumeModel.__tablename__, volumes_ids):
        # Refetch after lock
        res = await session.execute(
            select(VolumeModel)
            .where(
                VolumeModel.project_id == project.id,
                VolumeModel.id.in_(volumes_ids),
                VolumeModel.deleted == False,
                VolumeModel.lock_expires_at.is_(None),
            )
            .options(selectinload(VolumeModel.attachments))
            .execution_options(populate_existing=True)
            .order_by(VolumeModel.id)  # take locks in order
            .with_for_update(key_share=True, of=VolumeModel)
        )
        volume_models = res.scalars().unique().all()
        if len(volume_models) != len(volumes_ids):
            # TODO: Make the delete endpoint fully async so we don't need to lock and error:
            # put the request in queue and process in the background.
            raise ServerClientError(
                "Failed to delete volumes: volumes are being processed currently. Try again later."
            )
        for volume_model in volume_models:
            if len(volume_model.attachments) > 0:
                raise ServerClientError(
                    f"Failed to delete volume {volume_model.name}. Volume is in use."
                )
        for volume_model in volume_models:
            if not volume_model.to_be_deleted:
                volume_model.to_be_deleted = True
                events.emit(
                    session,
                    message="Volume marked for deletion",
                    actor=events.UserActor.from_user(user),
                    targets=[events.Target.from_model(volume_model)],
                )
        await session.commit()


async def _delete_volumes_sync(
    session: AsyncSession, project: ProjectModel, names: List[str], user: UserModel
):
    res = await session.execute(
        select(VolumeModel).where(
            VolumeModel.project_id == project.id,
            VolumeModel.name.in_(names),
            VolumeModel.deleted == False,
        )
    )
    volume_models = res.scalars().all()
    volumes_ids = sorted([v.id for v in volume_models])
    await session.commit()
    logger.info("Deleting volumes: %s", [v.name for v in volume_models])
    async with get_locker(get_db().dialect_name).lock_ctx(VolumeModel.__tablename__, volumes_ids):
        # Refetch after lock
        res = await session.execute(
            select(VolumeModel)
            .where(
                VolumeModel.project_id == project.id,
                VolumeModel.name.in_(names),
                VolumeModel.deleted == False,
            )
            .options(selectinload(VolumeModel.user))
            .options(selectinload(VolumeModel.attachments))
            .execution_options(populate_existing=True)
            .order_by(VolumeModel.id)  # take locks in order
            .with_for_update(key_share=True)
        )
        volume_models = res.scalars().unique().all()
        for volume_model in volume_models:
            if len(volume_model.attachments) > 0:
                raise ServerClientError(
                    f"Failed to delete volume {volume_model.name}. Volume is in use."
                )
        for volume_model in volume_models:
            try:
                await _delete_volume(session=session, project=project, volume_model=volume_model)
            except Exception:
                logger.exception("Error when deleting volume %s", volume_model.name)
            volume_model.deleted = True
            volume_model.deleted_at = common.get_current_datetime()
            events.emit(
                session,
                message="Volume deleted",
                actor=events.UserActor.from_user(user),
                targets=[events.Target.from_model(volume_model)],
            )
        await session.commit()


def volume_model_to_volume(volume_model: VolumeModel) -> Volume:
    configuration = get_volume_configuration(volume_model)
    vpd = get_volume_provisioning_data(volume_model)
    vad = get_volume_attachment_data(volume_model)
    # Initially VolumeProvisionigData lacked backend
    if vpd is not None and vpd.backend is None:
        vpd.backend = configuration.backend
    attachments = []
    for volume_attachment_model in volume_model.attachments:
        instance = volume_attachment_model.instance
        attachments.append(
            VolumeAttachment(
                instance=instance_model_to_volume_instance(instance),
                attachment_data=get_attachment_data(volume_attachment_model),
            )
        )
    deleted_at = None
    if volume_model.deleted_at is not None:
        deleted_at = volume_model.deleted_at
    volume = Volume(
        name=volume_model.name,
        project_name=volume_model.project.name,
        user=volume_model.user.name,
        configuration=configuration,
        external=configuration.volume_id is not None,
        created_at=volume_model.created_at,
        last_processed_at=volume_model.last_processed_at,
        status=volume_model.status,
        status_message=volume_model.status_message,
        deleted=volume_model.deleted,
        deleted_at=deleted_at,
        volume_id=vpd.volume_id if vpd is not None else None,
        provisioning_data=vpd,
        attachments=attachments,
        attachment_data=vad,
        id=volume_model.id,
    )
    volume.cost = _get_volume_cost(volume)
    return volume


def get_volume_configuration(volume_model: VolumeModel) -> VolumeConfiguration:
    return VolumeConfiguration.__response__.parse_raw(volume_model.configuration)


def get_volume_provisioning_data(volume_model: VolumeModel) -> Optional[VolumeProvisioningData]:
    if volume_model.volume_provisioning_data is None:
        return None
    return VolumeProvisioningData.__response__.parse_raw(volume_model.volume_provisioning_data)


def get_volume_attachment_data(volume_model: VolumeModel) -> Optional[VolumeAttachmentData]:
    if volume_model.volume_attachment_data is None:
        return None
    return VolumeAttachmentData.__response__.parse_raw(volume_model.volume_attachment_data)


def get_attachment_data(
    volume_attachment_model: VolumeAttachmentModel,
) -> Optional[VolumeAttachmentData]:
    if volume_attachment_model.attachment_data is None:
        return None
    return VolumeAttachmentData.__response__.parse_raw(volume_attachment_model.attachment_data)


def instance_model_to_volume_instance(instance_model: InstanceModel) -> VolumeInstance:
    instance_id = None
    jpd = get_instance_provisioning_data(instance_model)
    if jpd is not None:
        instance_id = jpd.instance_id
    return VolumeInstance(
        name=instance_model.name,
        fleet_name=instance_model.fleet.name if instance_model.fleet else None,
        instance_num=instance_model.instance_num,
        instance_id=instance_id,
    )


async def generate_volume_name(session: AsyncSession, project: ProjectModel) -> str:
    res = await session.execute(
        select(VolumeModel.name).where(
            VolumeModel.project_id == project.id,
            VolumeModel.deleted == False,
        )
    )
    names = set(res.scalars().all())
    while True:
        name = random_names.generate_name()
        if name not in names:
            return name


def _validate_volume_configuration(configuration: VolumeConfiguration):
    if configuration.volume_id is None and configuration.size is None:
        raise ServerClientError("Volume must specify either volume_id or size")
    backends_services.check_backend_type_available(configuration.backend)
    if configuration.backend not in BACKENDS_WITH_VOLUMES_SUPPORT:
        raise ServerClientError(
            f"Volumes are not supported for {configuration.backend.value} backend."
            f" Available backends with volumes support: {[b.value for b in BACKENDS_WITH_VOLUMES_SUPPORT]}."
        )
    if configuration.name is not None:
        validate_dstack_resource_name(configuration.name)

    if configuration.volume_id is not None and configuration.auto_cleanup_duration is not None:
        if (
            isinstance(configuration.auto_cleanup_duration, int)
            and configuration.auto_cleanup_duration > 0
        ) or (
            isinstance(configuration.auto_cleanup_duration, str)
            and configuration.auto_cleanup_duration not in ("off", "-1")
        ):
            raise ServerClientError(
                "External volumes (with volume_id) do not support auto_cleanup_duration. "
                "Auto-cleanup only works for volumes created and managed by dstack."
            )


async def _delete_volume(session: AsyncSession, project: ProjectModel, volume_model: VolumeModel):
    volume = volume_model_to_volume(volume_model)
    if volume.external:
        return

    if volume.provisioning_data is None:
        # The volume wasn't provisioned so there is nothing to delete
        return
    if volume.provisioning_data.backend is None:
        logger.error(
            f"Failed to delete volume {volume_model.name}. volume.provisioning_data.backend is None."
        )
        return

    try:
        backend = await backends_services.get_project_backend_by_type_or_error(
            project=volume_model.project,
            backend_type=volume.provisioning_data.backend,
        )
    except BackendNotAvailable:
        logger.error(
            f"Failed to delete volume {volume_model.name}. Backend {volume.configuration.backend} not available."
        )
        return

    compute = backend.compute()
    assert isinstance(compute, ComputeWithVolumeSupport)
    await common.run_async(
        compute.delete_volume,
        volume=volume,
    )


# Clouds charge volumes assuming 30-day months, e.g. https://aws.amazon.com/ebs/pricing/
_VOLUME_PRICING_PERIOD = timedelta(days=30)


def _get_volume_cost(volume: Volume) -> float:
    if volume.provisioning_data is None or volume.provisioning_data.price is None:
        return 0.0
    finished_at = common.get_current_datetime()
    if volume.deleted_at:
        finished_at = volume.deleted_at
    elif not volume.status.is_active():
        finished_at = volume.last_processed_at
    volume_age = finished_at - volume.created_at
    return (
        volume_age.total_seconds()
        * volume.provisioning_data.price
        / _VOLUME_PRICING_PERIOD.total_seconds()
    )


def _get_autocleanup_enabled(configuration: VolumeConfiguration) -> bool:
    auto_cleanup_duration = parse_duration(configuration.auto_cleanup_duration)
    return auto_cleanup_duration is not None and auto_cleanup_duration > 0
