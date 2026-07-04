import uuid
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.errors import ResourceExistsError, ServerClientError
from dstack._internal.core.models.common import ApplyAction
from dstack._internal.core.models.endpoints import (
    Endpoint,
    EndpointConfiguration,
    EndpointPlan,
    EndpointPlanJobOffers,
    EndpointPlanReplicaSpecGroup,
    EndpointPresetPolicy,
    EndpointProvisioningPlanAgent,
    EndpointProvisioningPlanNone,
    EndpointProvisioningPlanPreset,
    EndpointStatus,
)
from dstack._internal.core.models.runs import ServiceSpec
from dstack._internal.core.services import validate_dstack_resource_name
from dstack._internal.server.db import get_db, is_db_postgres, is_db_sqlite
from dstack._internal.server.models import (
    EndpointModel,
    EndpointRunSubmissionModel,
    ProjectModel,
    UserModel,
)
from dstack._internal.server.services import events
from dstack._internal.server.services.endpoints.agent import (
    AgentPlan,
    get_agent_service,
    get_agent_unavailable_reason,
    get_effective_max_agent_budget,
)
from dstack._internal.server.services.endpoints.planning import (
    EndpointPresetPlan,
    find_preset_planning_result,
)
from dstack._internal.server.services.locking import get_locker, string_to_lock_id
from dstack._internal.server.services.pipelines import PipelineHinterProtocol
from dstack._internal.server.services.projects import list_user_project_models
from dstack._internal.utils import common, random_names
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


def switch_endpoint_status(
    session: AsyncSession,
    endpoint_model: EndpointModel,
    new_status: EndpointStatus,
    actor: events.AnyActor = events.SystemActor(),
):
    old_status = endpoint_model.status
    if old_status == new_status:
        return

    endpoint_model.status = new_status
    emit_endpoint_status_change_event(
        session=session,
        endpoint_model=endpoint_model,
        old_status=old_status,
        new_status=new_status,
        status_message=endpoint_model.status_message,
        actor=actor,
    )


def emit_endpoint_status_change_event(
    session: AsyncSession,
    endpoint_model: EndpointModel,
    old_status: EndpointStatus,
    new_status: EndpointStatus,
    status_message: Optional[str],
    actor: events.AnyActor = events.SystemActor(),
) -> None:
    if old_status == new_status:
        return
    msg = get_endpoint_status_change_message(
        old_status=old_status,
        new_status=new_status,
        status_message=status_message,
    )
    events.emit(session, msg, actor=actor, targets=[events.Target.from_model(endpoint_model)])


def get_endpoint_status_change_message(
    old_status: EndpointStatus,
    new_status: EndpointStatus,
    status_message: Optional[str],
) -> str:
    msg = f"Endpoint status changed {old_status.upper()} -> {new_status.upper()}"
    if status_message is not None:
        msg += f" ({status_message})"
    return msg


async def list_endpoints(
    session: AsyncSession,
    user: UserModel,
    project_name: Optional[str],
    only_active: bool,
    prev_created_at: Optional[datetime],
    prev_id: Optional[uuid.UUID],
    limit: int,
    ascending: bool,
) -> List[Endpoint]:
    projects = await list_user_project_models(
        session=session,
        user=user,
        only_names=True,
    )
    if project_name is not None:
        projects = [p for p in projects if p.name == project_name]
    endpoint_models = await list_projects_endpoint_models(
        session=session,
        projects=projects,
        only_active=only_active,
        prev_created_at=prev_created_at,
        prev_id=prev_id,
        limit=limit,
        ascending=ascending,
    )
    return [endpoint_model_to_endpoint(e) for e in endpoint_models]


async def list_projects_endpoint_models(
    session: AsyncSession,
    projects: List[ProjectModel],
    only_active: bool,
    prev_created_at: Optional[datetime],
    prev_id: Optional[uuid.UUID],
    limit: int,
    ascending: bool,
) -> List[EndpointModel]:
    if not projects:
        return []
    filters: list[Any] = [EndpointModel.project_id.in_(p.id for p in projects)]
    if only_active:
        filters.append(EndpointModel.deleted == False)
    if prev_created_at is not None:
        if ascending:
            if prev_id is None:
                filters.append(EndpointModel.created_at > prev_created_at)
            else:
                filters.append(
                    or_(
                        EndpointModel.created_at > prev_created_at,
                        and_(
                            EndpointModel.created_at == prev_created_at,
                            EndpointModel.id < prev_id,
                        ),
                    )
                )
        else:
            if prev_id is None:
                filters.append(EndpointModel.created_at < prev_created_at)
            else:
                filters.append(
                    or_(
                        EndpointModel.created_at < prev_created_at,
                        and_(
                            EndpointModel.created_at == prev_created_at,
                            EndpointModel.id > prev_id,
                        ),
                    )
                )
    order_by = (EndpointModel.created_at.desc(), EndpointModel.id)
    if ascending:
        order_by = (EndpointModel.created_at.asc(), EndpointModel.id.desc())
    res = await session.execute(
        select(EndpointModel)
        .where(*filters)
        .order_by(*order_by)
        .limit(limit)
        .options(joinedload(EndpointModel.user))
        .options(joinedload(EndpointModel.project))
        .options(joinedload(EndpointModel.service_run))
    )
    return list(res.unique().scalars().all())


async def list_project_endpoints(
    session: AsyncSession,
    project: ProjectModel,
    names: Optional[List[str]] = None,
) -> List[Endpoint]:
    endpoint_models = await list_project_endpoint_models(
        session=session, project=project, names=names
    )
    return [endpoint_model_to_endpoint(e) for e in endpoint_models]


async def list_project_endpoint_models(
    session: AsyncSession,
    project: ProjectModel,
    names: Optional[List[str]] = None,
    include_deleted: bool = False,
) -> List[EndpointModel]:
    filters = [EndpointModel.project_id == project.id]
    if names is not None:
        filters.append(EndpointModel.name.in_(names))
    if not include_deleted:
        filters.append(EndpointModel.deleted == False)
    res = await session.execute(
        select(EndpointModel)
        .where(*filters)
        .options(joinedload(EndpointModel.user))
        .options(joinedload(EndpointModel.project))
        .options(joinedload(EndpointModel.service_run))
    )
    return list(res.unique().scalars().all())


async def get_endpoint_by_name(
    session: AsyncSession, project: ProjectModel, name: str
) -> Optional[Endpoint]:
    endpoint_model = await get_project_endpoint_model_by_name(
        session=session, project=project, name=name
    )
    if endpoint_model is None:
        return None
    return endpoint_model_to_endpoint(endpoint_model)


async def get_project_endpoint_model_by_name(
    session: AsyncSession,
    project: ProjectModel,
    name: str,
    include_deleted: bool = False,
) -> Optional[EndpointModel]:
    filters = [
        EndpointModel.name == name,
        EndpointModel.project_id == project.id,
    ]
    if not include_deleted:
        filters.append(EndpointModel.deleted == False)
    res = await session.execute(
        select(EndpointModel)
        .where(*filters)
        .options(joinedload(EndpointModel.user))
        .options(joinedload(EndpointModel.project))
        .options(joinedload(EndpointModel.service_run))
    )
    return res.unique().scalar_one_or_none()


async def get_endpoint_plan(
    session: AsyncSession,
    project: ProjectModel,
    user: UserModel,
    configuration: EndpointConfiguration,
    configuration_path: Optional[str],
) -> EndpointPlan:
    current_resource = None
    if configuration.name is not None:
        current_resource = await get_endpoint_by_name(
            session=session,
            project=project,
            name=configuration.name,
        )
        if current_resource is not None and current_resource.status.is_finished():
            current_resource = None
    preset_plan = None
    unprovisionable_preset_plan = None
    if configuration.preset_policy != EndpointPresetPolicy.CREATE:
        preset_planning_result = await find_preset_planning_result(
            session=session,
            project=project,
            user=user,
            endpoint_name=configuration.name,
            endpoint_configuration=configuration,
        )
        preset_plan = preset_planning_result.provisionable
        unprovisionable_preset_plan = preset_planning_result.unprovisionable
        if preset_plan is None and configuration.preset_policy == EndpointPresetPolicy.REUSE:
            preset_plan = unprovisionable_preset_plan
    provisioning_plan = _get_no_provisioning_plan(
        configuration.preset_policy,
        unprovisionable_preset_plan=unprovisionable_preset_plan,
    )
    if preset_plan is not None:
        provisioning_plan = _endpoint_preset_plan_to_provisioning_plan(preset_plan)
    elif (
        configuration.preset_policy != EndpointPresetPolicy.REUSE
        and get_agent_service().is_enabled()
    ):
        provisioning_plan = _agent_plan_to_provisioning_plan(
            get_agent_service().get_plan(),
            max_budget=get_effective_max_agent_budget(configuration),
            reason=_get_unprovisionable_preset_reason(unprovisionable_preset_plan),
        )
    return EndpointPlan(
        project_name=project.name,
        user=user.name,
        configuration=configuration,
        configuration_path=configuration_path,
        current_resource=current_resource,
        action=ApplyAction.CREATE if current_resource is None else ApplyAction.UPDATE,
        preset_policy=configuration.preset_policy,
        provisioning_plan=provisioning_plan,
    )


def _agent_plan_to_provisioning_plan(
    agent_plan: AgentPlan,
    max_budget: Optional[float],
    reason: Optional[str] = None,
) -> EndpointProvisioningPlanAgent:
    return EndpointProvisioningPlanAgent(
        agent_model=agent_plan.model,
        max_budget=max_budget,
        reason=reason,
    )


def _get_no_provisioning_plan(
    preset_policy: EndpointPresetPolicy,
    unprovisionable_preset_plan: Optional[EndpointPresetPlan] = None,
) -> EndpointProvisioningPlanNone:
    if preset_policy == EndpointPresetPolicy.REUSE:
        reason = _get_unprovisionable_preset_reason(unprovisionable_preset_plan)
        if reason is None:
            reason = "No matching endpoint presets found."
        return EndpointProvisioningPlanNone(reason=reason)
    agent_unavailable_reason = get_agent_unavailable_reason()
    preset_reason = _get_unprovisionable_preset_reason(unprovisionable_preset_plan)
    if preset_policy == EndpointPresetPolicy.REUSE_OR_CREATE:
        if preset_reason is not None:
            return EndpointProvisioningPlanNone(
                reason=(
                    f"{preset_reason} Creating a preset requires the server agent, "
                    f"but {agent_unavailable_reason}"
                )
            )
        return EndpointProvisioningPlanNone(
            reason=(
                "No matching endpoint presets found. Creating a preset requires the server "
                f"agent, but {agent_unavailable_reason}"
            )
        )
    return EndpointProvisioningPlanNone(
        reason=(f"Preset policy create requires the server agent, but {agent_unavailable_reason}")
    )


def _get_unprovisionable_preset_reason(
    preset_plan: Optional[EndpointPresetPlan],
) -> Optional[str]:
    if preset_plan is None:
        return None
    return f"Endpoint preset {preset_plan.preset.name} matched but has no available offers."


def _endpoint_preset_plan_to_provisioning_plan(
    preset_plan: EndpointPresetPlan,
) -> EndpointProvisioningPlanPreset:
    run_spec = preset_plan.run_plan.get_effective_run_spec()
    service_name = run_spec.run_name or run_spec.configuration.name or "(generated)"
    return EndpointProvisioningPlanPreset(
        preset_name=preset_plan.preset.name,
        service_name=service_name,
        replica_spec_groups=[
            EndpointPlanReplicaSpecGroup(
                name=group.name,
                resources=group.resources,
                tested_resources=group.tested_resources,
            )
            for group in preset_plan.preset.replica_spec_groups
        ],
        job_offers=[
            EndpointPlanJobOffers(
                replica_group=job_plan.job_spec.replica_group,
                resources=job_plan.job_spec.requirements.resources,
                spot=job_plan.job_spec.requirements.spot,
                max_price=job_plan.job_spec.requirements.max_price,
                offers=job_plan.offers,
                total_offers=job_plan.total_offers,
                max_offer_price=job_plan.max_price,
            )
            for job_plan in preset_plan.run_plan.job_plans
        ],
    )


async def create_endpoint(
    session: AsyncSession,
    project: ProjectModel,
    user: UserModel,
    configuration: EndpointConfiguration,
    pipeline_hinter: PipelineHinterProtocol,
) -> Endpoint:
    _validate_endpoint_configuration(configuration)

    lock_namespace = f"endpoint_names_{project.name}"
    if is_db_sqlite():
        await session.commit()
    elif is_db_postgres():
        await session.execute(
            select(func.pg_advisory_xact_lock(string_to_lock_id(lock_namespace)))
        )
    lock, _ = get_locker(get_db().dialect_name).get_lockset(lock_namespace)
    async with lock:
        now = common.get_current_datetime()
        if configuration.name is not None:
            endpoint_model = await get_project_endpoint_model_by_name(
                session=session,
                project=project,
                name=configuration.name,
            )
            if endpoint_model is not None:
                if not endpoint_model.status.is_finished():
                    raise ResourceExistsError()
                endpoint_model.deleted = True
                endpoint_model.deleted_at = now
        else:
            configuration.name = await generate_endpoint_name(session=session, project=project)

        endpoint_model = EndpointModel(
            id=uuid.uuid4(),
            name=configuration.name,
            project=project,
            user_id=user.id,
            status=EndpointStatus.SUBMITTED,
            configuration=configuration.json(),
            created_at=now,
            last_processed_at=now,
        )
        session.add(endpoint_model)
        events.emit(
            session,
            message=f"Endpoint created. Status: {endpoint_model.status.upper()}",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(endpoint_model)],
        )
        await session.commit()
        pipeline_hinter.hint_fetch(EndpointModel.__name__)
        return endpoint_model_to_endpoint(endpoint_model)


async def delete_endpoints(
    session: AsyncSession,
    project: ProjectModel,
    names: List[str],
    user: UserModel,
    pipeline_hinter: Optional[PipelineHinterProtocol] = None,
):
    endpoint_models = await list_project_endpoint_models(
        session=session,
        project=project,
        names=names,
    )
    now = common.get_current_datetime()
    for endpoint_model in endpoint_models:
        if endpoint_model.to_be_deleted:
            continue
        endpoint_model.to_be_deleted = True
        endpoint_model.deletion_requested_at = now
        events.emit(
            session,
            message="Endpoint marked for deletion",
            actor=events.UserActor.from_user(user),
            targets=[events.Target.from_model(endpoint_model)],
        )
    await session.commit()
    if pipeline_hinter is not None:
        pipeline_hinter.hint_fetch(EndpointModel.__name__)


def endpoint_model_to_endpoint(endpoint_model: EndpointModel) -> Endpoint:
    configuration = get_endpoint_configuration(endpoint_model)
    run_name = None
    url = None
    status = endpoint_model.status
    if status == EndpointStatus.ACTIVE:
        status = EndpointStatus.RUNNING
    if endpoint_model.service_run is not None and not endpoint_model.service_run.deleted:
        run_name = endpoint_model.service_run.run_name
        if endpoint_model.service_run.service_spec is not None:
            service_spec = ServiceSpec.__response__.parse_raw(
                endpoint_model.service_run.service_spec
            )
            if service_spec.model is not None:
                url = service_spec.model.base_url
    return Endpoint(
        id=endpoint_model.id,
        name=endpoint_model.name,
        project_name=endpoint_model.project.name,
        user=endpoint_model.user.name,
        configuration=configuration,
        created_at=endpoint_model.created_at,
        last_processed_at=endpoint_model.last_processed_at,
        status=status,
        status_message=endpoint_model.status_message,
        deleted=endpoint_model.deleted,
        deleted_at=endpoint_model.deleted_at,
        run_name=run_name,
        url=url,
        error=endpoint_model.status_message if status == EndpointStatus.FAILED else None,
    )


def get_endpoint_configuration(endpoint_model: EndpointModel) -> EndpointConfiguration:
    return EndpointConfiguration.__response__.parse_raw(endpoint_model.configuration)


async def record_endpoint_run_submission(
    session: AsyncSession,
    endpoint_id: uuid.UUID,
    run_id: uuid.UUID,
) -> EndpointRunSubmissionModel:
    existing_submission = await _get_endpoint_run_submission_by_run_id(
        session=session,
        run_id=run_id,
    )
    if existing_submission is not None:
        if existing_submission.endpoint_id != endpoint_id:
            raise ServerClientError("Run is already recorded for another endpoint")
        return existing_submission

    res = await session.execute(
        select(func.max(EndpointRunSubmissionModel.submission_num)).where(
            EndpointRunSubmissionModel.endpoint_id == endpoint_id
        )
    )
    submission_num = (res.scalar_one_or_none() or 0) + 1
    submission = EndpointRunSubmissionModel(
        endpoint_id=endpoint_id,
        run_id=run_id,
        submission_num=submission_num,
        submitted_at=common.get_current_datetime(),
    )
    session.add(submission)
    await session.flush()
    return submission


async def _get_endpoint_run_submission_by_run_id(
    session: AsyncSession,
    run_id: uuid.UUID,
) -> Optional[EndpointRunSubmissionModel]:
    res = await session.execute(
        select(EndpointRunSubmissionModel).where(EndpointRunSubmissionModel.run_id == run_id)
    )
    return res.scalar_one_or_none()


async def generate_endpoint_name(session: AsyncSession, project: ProjectModel) -> str:
    res = await session.execute(
        select(EndpointModel.name).where(
            EndpointModel.project_id == project.id,
            EndpointModel.deleted == False,
        )
    )
    names = set(res.scalars().all())
    while True:
        name = random_names.generate_name()
        if name not in names:
            return name


def _validate_endpoint_configuration(configuration: EndpointConfiguration):
    if not configuration.model.strip():
        raise ServerClientError("Endpoint must specify model")
    if configuration.name is not None:
        validate_dstack_resource_name(configuration.name)
    try:
        configuration.env.as_dict()
    except ValueError as e:
        raise ServerClientError(f"Endpoint env is unresolved: {e}") from e
