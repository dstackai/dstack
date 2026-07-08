import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional, Sequence

from pydantic import ValidationError
from sqlalchemy import or_, select, update
from sqlalchemy.orm import joinedload, load_only

from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.endpoints import EndpointPresetPolicy, EndpointStatus
from dstack._internal.core.models.runs import (
    ApplyRunPlanInput,
    JobStatus,
    RunSpec,
    RunStatus,
    ServiceSpec,
)
from dstack._internal.server.background.pipeline_tasks.base import (
    Fetcher,
    Heartbeater,
    ItemUpdateMap,
    Pipeline,
    PipelineItem,
    Worker,
    log_lock_token_changed_after_processing,
    log_lock_token_mismatch,
    resolve_now_placeholders,
    set_processed_update_map_fields,
    set_unlock_update_map_fields,
)
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import (
    EndpointModel,
    EndpointRunSubmissionModel,
    ProjectModel,
    RunModel,
    UserModel,
)
from dstack._internal.server.services import runs as runs_services
from dstack._internal.server.services.endpoints import (
    can_use_endpoint_agent,
    emit_endpoint_status_change_event,
    get_endpoint_agent_admin_required_message,
    get_endpoint_configuration,
    get_endpoint_no_fleets_message,
    has_endpoint_existing_usable_fleets,
    record_endpoint_run_submission,
)
from dstack._internal.server.services.endpoints.agent import (
    abort_agent_endpoint,
    get_agent_service,
    get_agent_unavailable_reason,
)
from dstack._internal.server.services.endpoints.names import get_endpoint_serving_run_name
from dstack._internal.server.services.endpoints.planning import find_preset_planning_result
from dstack._internal.server.services.endpoints.preset_building import (
    build_endpoint_preset_from_run,
)
from dstack._internal.server.services.endpoints.presets import get_endpoint_preset_service
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.services.pipelines import PipelineHinterProtocol
from dstack._internal.server.utils import sentry_utils
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

_NO_MATCHING_PRESET_MESSAGE = "No matching endpoint presets found."
_MAX_AGENT_STATUS_MESSAGE_CHARS = 500


@dataclass
class EndpointPipelineItem(PipelineItem):
    status: EndpointStatus


class EndpointPipeline(Pipeline[EndpointPipelineItem]):
    def __init__(
        self,
        workers_num: int = 4,
        queue_lower_limit_factor: float = 0.5,
        queue_upper_limit_factor: float = 2.0,
        min_processing_interval: timedelta = timedelta(seconds=10),
        lock_timeout: timedelta = timedelta(seconds=30),
        heartbeat_trigger: timedelta = timedelta(seconds=15),
        *,
        pipeline_hinter: PipelineHinterProtocol,
    ) -> None:
        super().__init__(
            workers_num=workers_num,
            queue_lower_limit_factor=queue_lower_limit_factor,
            queue_upper_limit_factor=queue_upper_limit_factor,
            min_processing_interval=min_processing_interval,
            lock_timeout=lock_timeout,
            heartbeat_trigger=heartbeat_trigger,
        )
        self.__heartbeater = Heartbeater[EndpointPipelineItem](
            model_type=EndpointModel,
            lock_timeout=self._lock_timeout,
            heartbeat_trigger=self._heartbeat_trigger,
        )
        self.__fetcher = EndpointFetcher(
            queue=self._queue,
            queue_desired_minsize=self._queue_desired_minsize,
            min_processing_interval=self._min_processing_interval,
            lock_timeout=self._lock_timeout,
            heartbeater=self._heartbeater,
        )
        self.__workers = [
            EndpointWorker(
                queue=self._queue,
                heartbeater=self._heartbeater,
                pipeline_hinter=pipeline_hinter,
            )
            for _ in range(self._workers_num)
        ]

    @property
    def hint_fetch_model_name(self) -> str:
        return EndpointModel.__name__

    @property
    def _heartbeater(self) -> Heartbeater[EndpointPipelineItem]:
        return self.__heartbeater

    @property
    def _fetcher(self) -> Fetcher[EndpointPipelineItem]:
        return self.__fetcher

    @property
    def _workers(self) -> Sequence["EndpointWorker"]:
        return self.__workers


class EndpointFetcher(Fetcher[EndpointPipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[EndpointPipelineItem],
        queue_desired_minsize: int,
        min_processing_interval: timedelta,
        lock_timeout: timedelta,
        heartbeater: Heartbeater[EndpointPipelineItem],
        queue_check_delay: float = 1.0,
    ) -> None:
        super().__init__(
            queue=queue,
            queue_desired_minsize=queue_desired_minsize,
            min_processing_interval=min_processing_interval,
            lock_timeout=lock_timeout,
            heartbeater=heartbeater,
            queue_check_delay=queue_check_delay,
        )

    @sentry_utils.instrument_pipeline_task("EndpointFetcher.fetch")
    async def fetch(self, limit: int) -> list[EndpointPipelineItem]:
        endpoint_lock, _ = get_locker(get_db().dialect_name).get_lockset(
            EndpointModel.__tablename__
        )
        async with endpoint_lock:
            async with get_session_ctx() as session:
                now = get_current_datetime()
                res = await session.execute(
                    select(EndpointModel)
                    .where(
                        EndpointModel.status.in_(
                            [
                                EndpointStatus.SUBMITTED,
                                EndpointStatus.PROVISIONING,
                                EndpointStatus.PROTOTYPING,
                                EndpointStatus.RUNNING,
                                EndpointStatus.STOPPING,
                            ]
                        ),
                        or_(
                            EndpointModel.last_processed_at <= now - self._min_processing_interval,
                            EndpointModel.last_processed_at == EndpointModel.created_at,
                        ),
                        or_(
                            EndpointModel.lock_expires_at.is_(None),
                            EndpointModel.lock_expires_at < now,
                        ),
                        or_(
                            EndpointModel.lock_owner.is_(None),
                            EndpointModel.lock_owner == EndpointPipeline.__name__,
                        ),
                    )
                    .order_by(EndpointModel.last_processed_at.asc())
                    .limit(limit)
                    .with_for_update(skip_locked=True, key_share=True, of=EndpointModel)
                    .options(
                        load_only(
                            EndpointModel.id,
                            EndpointModel.lock_token,
                            EndpointModel.lock_expires_at,
                            EndpointModel.status,
                        )
                    )
                )
                endpoint_models = list(res.scalars().all())
                lock_expires_at = get_current_datetime() + self._lock_timeout
                lock_token = uuid.uuid4()
                items = []
                for endpoint_model in endpoint_models:
                    prev_lock_expired = endpoint_model.lock_expires_at is not None
                    endpoint_model.lock_expires_at = lock_expires_at
                    endpoint_model.lock_token = lock_token
                    endpoint_model.lock_owner = EndpointPipeline.__name__
                    items.append(
                        EndpointPipelineItem(
                            __tablename__=EndpointModel.__tablename__,
                            id=endpoint_model.id,
                            lock_expires_at=lock_expires_at,
                            lock_token=lock_token,
                            prev_lock_expired=prev_lock_expired,
                            status=endpoint_model.status,
                        )
                    )
                await session.commit()
        return items


class EndpointWorker(Worker[EndpointPipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[EndpointPipelineItem],
        heartbeater: Heartbeater[EndpointPipelineItem],
        pipeline_hinter: PipelineHinterProtocol,
    ) -> None:
        super().__init__(
            queue=queue,
            heartbeater=heartbeater,
            pipeline_hinter=pipeline_hinter,
        )

    @sentry_utils.instrument_pipeline_task("EndpointWorker.process")
    async def process(self, item: EndpointPipelineItem):
        endpoint_model = await _refetch_locked_endpoint(item)
        if endpoint_model is None:
            log_lock_token_mismatch(logger, item)
            return

        if endpoint_model.status == EndpointStatus.SUBMITTED:
            result = await _process_submitted_endpoint(
                endpoint_model=endpoint_model,
                pipeline_hinter=self._pipeline_hinter,
            )
        elif endpoint_model.status == EndpointStatus.PROVISIONING:
            result = await _process_provisioning_endpoint(
                endpoint_model=endpoint_model,
                pipeline_hinter=self._pipeline_hinter,
            )
        elif endpoint_model.status == EndpointStatus.PROTOTYPING:
            result = await _process_prototyping_endpoint(
                endpoint_model=endpoint_model,
                pipeline_hinter=self._pipeline_hinter,
            )
        elif endpoint_model.status == EndpointStatus.STOPPING:
            result = await _process_stopping_endpoint(
                endpoint_model=endpoint_model,
                pipeline_hinter=self._pipeline_hinter,
            )
        elif endpoint_model.status == EndpointStatus.RUNNING:
            result = await _process_running_endpoint(endpoint_model)
        else:
            result = _ProcessResult()

        runs_to_stop = await _get_endpoint_runs_to_stop_after_failure(endpoint_model, result)
        for run_to_stop in runs_to_stop:
            logger.info(
                "Stopping backing run %s after endpoint %s failed",
                run_to_stop.run_name,
                endpoint_model.name,
            )
            await _stop_backing_run(
                endpoint_model=endpoint_model,
                run_name=run_to_stop.run_name,
                pipeline_hinter=self._pipeline_hinter,
            )

        await _apply_process_result(item=item, endpoint_model=endpoint_model, result=result)


async def _refetch_locked_endpoint(item: EndpointPipelineItem) -> Optional[EndpointModel]:
    async with get_session_ctx() as session:
        res = await session.execute(
            select(EndpointModel)
            .where(
                EndpointModel.id == item.id,
                EndpointModel.lock_token == item.lock_token,
            )
            .options(joinedload(EndpointModel.project).joinedload(ProjectModel.backends))
            .options(joinedload(EndpointModel.project).joinedload(ProjectModel.members))
            .options(
                joinedload(EndpointModel.user).load_only(
                    UserModel.name,
                    UserModel.global_role,
                    UserModel.token,
                )
            )
            .options(joinedload(EndpointModel.service_run).selectinload(RunModel.jobs))
        )
        return res.unique().scalar_one_or_none()


async def _apply_process_result(
    item: EndpointPipelineItem,
    endpoint_model: EndpointModel,
    result: "_ProcessResult",
):
    update_map = _EndpointUpdateMap()
    update_map.update(result.update_map)
    set_processed_update_map_fields(update_map)
    set_unlock_update_map_fields(update_map)

    async with get_session_ctx() as session:
        resolve_now_placeholders(update_map, now=get_current_datetime())
        res = await session.execute(
            update(EndpointModel)
            .where(
                EndpointModel.id == endpoint_model.id,
                EndpointModel.lock_token == endpoint_model.lock_token,
                EndpointModel.status == item.status,
            )
            .values(**update_map)
            .returning(EndpointModel.id)
        )
        updated_ids = list(res.scalars().all())
        if len(updated_ids) == 0:
            if await _link_reported_service_run_to_stopping_endpoint(session, item, result):
                return
            logger.info(
                "Endpoint %s changed while being processed; ignoring stale result",
                endpoint_model.name,
            )
            return
        emit_endpoint_status_change_event(
            session=session,
            endpoint_model=endpoint_model,
            old_status=endpoint_model.status,
            new_status=update_map.get("status", endpoint_model.status),
            status_message=update_map.get("status_message", endpoint_model.status_message),
        )


async def _link_reported_service_run_to_stopping_endpoint(
    session,
    item: EndpointPipelineItem,
    result: "_ProcessResult",
) -> bool:
    service_run_id = result.update_map.get("service_run_id")
    if service_run_id is None:
        return False

    update_map = _EndpointUpdateMap(service_run_id=service_run_id)
    set_processed_update_map_fields(update_map)
    set_unlock_update_map_fields(update_map)

    resolve_now_placeholders(update_map, now=get_current_datetime())
    res = await session.execute(
        update(EndpointModel)
        .where(
            EndpointModel.id == item.id,
            EndpointModel.lock_token == item.lock_token,
            EndpointModel.status == EndpointStatus.STOPPING,
            EndpointModel.service_run_id.is_(None),
        )
        .values(**update_map)
        .returning(EndpointModel.id)
    )
    updated_ids = list(res.scalars().all())
    if len(updated_ids) == 0:
        log_lock_token_changed_after_processing(logger, item)
        return False
    logger.info(
        "Linked reported service run %s to stopping endpoint %s",
        service_run_id,
        item.id,
    )
    return True


class _EndpointUpdateMap(ItemUpdateMap, total=False):
    status: EndpointStatus
    status_message: Optional[str]
    service_run_id: uuid.UUID
    provisioning_method: Optional[str]


@dataclass
class _ProcessResult:
    update_map: _EndpointUpdateMap = field(default_factory=_EndpointUpdateMap)


@dataclass(frozen=True)
class _PresetSubmission:
    run_id: uuid.UUID
    preset_model: str
    recipe_id: str


@dataclass(frozen=True)
class _PresetSubmissionResult:
    submission: Optional[_PresetSubmission] = None
    unprovisionable_preset: Optional[str] = None


async def _get_endpoint_runs_to_stop_after_failure(
    endpoint_model: EndpointModel,
    result: _ProcessResult,
) -> list[RunModel]:
    if result.update_map.get("status") != EndpointStatus.FAILED:
        return []
    return [
        run
        for run in await _get_endpoint_unfinished_runs(endpoint_model)
        if run.status != RunStatus.TERMINATING
    ]


async def _get_endpoint_unfinished_runs(endpoint_model: EndpointModel) -> list[RunModel]:
    runs: list[RunModel] = []
    seen_run_ids: set[uuid.UUID] = set()
    if endpoint_model.service_run is not None:
        runs.append(endpoint_model.service_run)
        seen_run_ids.add(endpoint_model.service_run.id)
    async with get_session_ctx() as session:
        res = await session.execute(
            select(RunModel)
            .join(
                EndpointRunSubmissionModel,
                EndpointRunSubmissionModel.run_id == RunModel.id,
            )
            .where(
                EndpointRunSubmissionModel.endpoint_id == endpoint_model.id,
                RunModel.deleted == False,
            )
        )
        runs.extend(run for run in res.unique().scalars().all() if run.id not in seen_run_ids)
    return [run for run in runs if not run.deleted and not run.status.is_finished()]


async def _process_submitted_endpoint(
    endpoint_model: EndpointModel,
    pipeline_hinter: PipelineHinterProtocol,
) -> _ProcessResult:
    endpoint_configuration = get_endpoint_configuration(endpoint_model)
    async with get_session_ctx() as session:
        has_usable_fleets = await has_endpoint_existing_usable_fleets(
            session=session,
            project=endpoint_model.project,
            configuration=endpoint_configuration,
        )
    if not has_usable_fleets:
        return _ProcessResult(
            update_map={
                "status": EndpointStatus.FAILED,
                "status_message": get_endpoint_no_fleets_message(endpoint_configuration),
            }
        )
    try:
        submission_result = await _submit_endpoint_from_preset(
            endpoint_id=endpoint_model.id,
            pipeline_hinter=pipeline_hinter,
        )
    except ServerClientError as e:
        return _ProcessResult(
            update_map={
                "status": EndpointStatus.FAILED,
                "status_message": e.msg,
            }
        )
    if submission_result.submission is not None:
        logger.info(
            "Provisioning endpoint %s from preset %s recipe %s",
            endpoint_model.name,
            submission_result.submission.preset_model,
            submission_result.submission.recipe_id,
        )
        update_map = _EndpointUpdateMap(
            status=EndpointStatus.PROVISIONING,
            status_message=None,
            service_run_id=submission_result.submission.run_id,
            provisioning_method=(
                f"preset:{submission_result.submission.preset_model}"
                f"#{submission_result.submission.recipe_id}"
            ),
        )
        return _ProcessResult(update_map=update_map)

    if await _should_provision_with_agent(endpoint_model):
        logger.info("Provisioning endpoint %s with server agent", endpoint_model.name)
        update_map = _EndpointUpdateMap(
            status=EndpointStatus.PROTOTYPING,
            status_message=None,
            provisioning_method="agent",
        )
        return _ProcessResult(update_map=update_map)

    logger.info("Failing endpoint %s: no preset path is available", endpoint_model.name)
    return _ProcessResult(
        update_map={
            "status": EndpointStatus.FAILED,
            "status_message": _get_no_provisioning_path_message(
                endpoint_model,
                unprovisionable_preset=submission_result.unprovisionable_preset,
            ),
        }
    )


async def _should_provision_with_agent(endpoint_model: EndpointModel) -> bool:
    endpoint_configuration = get_endpoint_configuration(endpoint_model)
    if endpoint_configuration.preset_policy == EndpointPresetPolicy.REUSE:
        return False
    if not get_agent_service().is_enabled():
        return False
    if not can_use_endpoint_agent(user=endpoint_model.user, project=endpoint_model.project):
        return False
    async with get_session_ctx() as session:
        return await has_endpoint_existing_usable_fleets(
            session=session,
            project=endpoint_model.project,
            configuration=endpoint_configuration,
        )


async def _get_active_serving_run_name_conflict(
    endpoint_model: EndpointModel,
) -> Optional[_ProcessResult]:
    serving_run_name = get_endpoint_serving_run_name(endpoint_model.name)
    assert serving_run_name is not None
    async with get_session_ctx() as session:
        run_model = await runs_services.get_run_model_by_name(
            session=session,
            project=endpoint_model.project,
            run_name=serving_run_name,
        )
    if run_model is None:
        return None
    if endpoint_model.service_run_id == run_model.id:
        return None
    if run_model.status.is_finished():
        return None
    return _ProcessResult(
        update_map={
            "status": EndpointStatus.FAILED,
            "status_message": f"Run name '{serving_run_name}' is taken by an existing run",
        }
    )


async def _process_provisioning_endpoint(
    endpoint_model: EndpointModel,
    pipeline_hinter: PipelineHinterProtocol,
) -> _ProcessResult:
    if endpoint_model.service_run is None:
        if endpoint_model.provisioning_method == "agent":
            return await _process_prototyping_endpoint(
                endpoint_model=endpoint_model,
                pipeline_hinter=pipeline_hinter,
            )
        conflict_result = await _get_active_serving_run_name_conflict(endpoint_model)
        if conflict_result is not None:
            return conflict_result

    readiness = _get_backing_service_readiness(endpoint_model)
    if readiness.failed_message is not None:
        return _ProcessResult(
            update_map={
                "status": EndpointStatus.FAILED,
                "status_message": readiness.failed_message,
            }
        )
    if readiness.model_base_url is None or readiness.model_name is None:
        return _ProcessResult()
    if endpoint_model.provisioning_method == "agent":
        # The agent's final report is the functional signal. This server-side gate only
        # confirms that the verified run still looks like a normal ready dstack service.
        await _try_save_agent_endpoint_preset(
            endpoint_model=endpoint_model,
        )
        if endpoint_model.service_run_id is not None:
            await _stop_non_final_submitted_runs(
                endpoint_model=endpoint_model,
                final_run_id=endpoint_model.service_run_id,
                pipeline_hinter=pipeline_hinter,
            )
    return _ProcessResult(
        update_map={
            "status": EndpointStatus.RUNNING,
            "status_message": None,
        }
    )


async def _process_prototyping_endpoint(
    endpoint_model: EndpointModel,
    pipeline_hinter: PipelineHinterProtocol,
) -> _ProcessResult:
    if endpoint_model.service_run is not None:
        return await _process_agent_verified_endpoint(
            endpoint_model=endpoint_model,
            pipeline_hinter=pipeline_hinter,
        )
    return await _provision_endpoint_with_agent(
        endpoint_model=endpoint_model,
        pipeline_hinter=pipeline_hinter,
    )


async def _process_agent_verified_endpoint(
    endpoint_model: EndpointModel,
    pipeline_hinter: PipelineHinterProtocol,
) -> _ProcessResult:
    run_model = endpoint_model.service_run
    if run_model is None:
        return _ProcessResult()
    readiness = _get_service_run_readiness(run_model, endpoint_name=endpoint_model.name)
    if readiness.failed_message is not None:
        return _ProcessResult(
            update_map={
                "status": EndpointStatus.FAILED,
                "status_message": readiness.failed_message,
            }
        )
    if readiness.model_base_url is None or readiness.model_name is None:
        return _ProcessResult(update_map={"status": EndpointStatus.PROTOTYPING})
    await _save_agent_endpoint_preset(
        endpoint_model=endpoint_model,
        run_model=run_model,
    )
    await _stop_non_final_submitted_runs(
        endpoint_model=endpoint_model,
        final_run_id=run_model.id,
        pipeline_hinter=pipeline_hinter,
    )
    return _ProcessResult(
        update_map={
            "status": EndpointStatus.RUNNING,
            "status_message": None,
        }
    )


async def _provision_endpoint_with_agent(
    endpoint_model: EndpointModel,
    pipeline_hinter: PipelineHinterProtocol,
) -> _ProcessResult:
    agent_service = get_agent_service()
    if not agent_service.is_enabled():
        return _ProcessResult(
            update_map={
                "status": EndpointStatus.FAILED,
                "status_message": _get_no_provisioning_path_message(endpoint_model),
            }
        )

    result = await agent_service.provision_endpoint(
        endpoint_model=endpoint_model,
        pipeline_hinter=pipeline_hinter,
    )
    await _record_agent_submitted_runs(
        endpoint_model=endpoint_model,
        submitted_run_ids=result.submitted_run_ids,
        submitted_run_names=result.submitted_run_names,
    )
    if result.in_progress:
        return _ProcessResult(
            update_map={
                "status": EndpointStatus.PROTOTYPING,
                "status_message": None,
            }
        )
    if result.error is not None:
        return _ProcessResult(
            update_map={
                "status": EndpointStatus.FAILED,
                "status_message": _format_agent_status_message(result.error),
            }
        )
    report = result.final_report
    if report is None:
        return _ProcessResult(
            update_map={
                "status": EndpointStatus.FAILED,
                "status_message": "Server agent did not return a final report",
            }
        )
    if not report.success:
        return _ProcessResult(
            update_map={
                "status": EndpointStatus.FAILED,
                "status_message": _format_agent_status_message(
                    report.failure_summary,
                    default="Server agent did not verify the endpoint",
                ),
            }
        )
    run_id = result.run_id or report.run_id
    if result.run_id is not None and report.run_id is not None and result.run_id != report.run_id:
        return _ProcessResult(
            update_map={
                "status": EndpointStatus.FAILED,
                "status_message": "Server agent returned inconsistent run id in final report",
            }
        )
    if (
        result.run_name is not None
        and report.run_name is not None
        and result.run_name != report.run_name
    ):
        return _ProcessResult(
            update_map={
                "status": EndpointStatus.FAILED,
                "status_message": ("Server agent returned inconsistent run name in final report"),
            }
        )
    if run_id is None:
        return _ProcessResult(
            update_map={
                "status": EndpointStatus.FAILED,
                "status_message": "Server agent final report did not identify a run id",
            }
        )

    async with get_session_ctx() as session:
        res = await session.execute(
            select(RunModel)
            .where(
                RunModel.id == run_id,
                RunModel.project_id == endpoint_model.project_id,
                RunModel.deleted == False,
            )
            .options(joinedload(RunModel.user))
            .options(joinedload(RunModel.jobs))
        )
        run_model = res.unique().scalar_one_or_none()
    if run_model is None:
        return _ProcessResult(
            update_map={
                "status": EndpointStatus.FAILED,
                "status_message": (f"Server agent reported run '{run_id}' but it was not found"),
            }
        )
    if report.run_name is not None and report.run_name != run_model.run_name:
        return _ProcessResult(
            update_map={
                "status": EndpointStatus.FAILED,
                "status_message": ("Server agent returned inconsistent run name in final report"),
            }
        )
    if not _is_valid_agent_submission_run_name(endpoint_model.name, run_model.run_name):
        return _ProcessResult(
            update_map={
                "status": EndpointStatus.FAILED,
                "status_message": (
                    "Server agent final service run name must be "
                    f"'{endpoint_model.name}-<submission-number>'"
                ),
            }
        )
    if run_model.user_id != endpoint_model.user_id:
        return _ProcessResult(
            update_map={
                "status": EndpointStatus.FAILED,
                "status_message": f"Run '{run_model.run_name}' is not owned by the endpoint user",
            }
        )
    try:
        run_spec = RunSpec.__response__.parse_raw(run_model.run_spec)
    except ValidationError:
        return _ProcessResult(
            update_map={
                "status": EndpointStatus.FAILED,
                "status_message": f"Run '{run_model.run_name}' has invalid run spec",
            }
        )
    if not isinstance(run_spec.configuration, ServiceConfiguration):
        return _ProcessResult(
            update_map={
                "status": EndpointStatus.FAILED,
                "status_message": f"Run '{run_model.run_name}' is not a service",
            }
        )
    try:
        await _record_endpoint_run_submission(
            endpoint_id=endpoint_model.id,
            run_id=run_model.id,
        )
    except ServerClientError as e:
        return _ProcessResult(
            update_map={
                "status": EndpointStatus.FAILED,
                "status_message": e.msg,
            }
        )
    readiness = _get_service_run_readiness(run_model, endpoint_name=endpoint_model.name)
    if readiness.failed_message is not None:
        return _ProcessResult(
            update_map={
                "status": EndpointStatus.FAILED,
                "status_message": readiness.failed_message,
            }
        )
    if readiness.model_base_url is None or readiness.model_name is None:
        return _ProcessResult(
            update_map={
                "status": EndpointStatus.PROTOTYPING,
                "status_message": None,
                "service_run_id": run_model.id,
            }
        )
    await _save_agent_endpoint_preset(
        endpoint_model=endpoint_model,
        run_model=run_model,
    )
    await _stop_non_final_submitted_runs(
        endpoint_model=endpoint_model,
        final_run_id=run_model.id,
        pipeline_hinter=pipeline_hinter,
    )
    return _ProcessResult(
        update_map={
            "status": EndpointStatus.RUNNING,
            "status_message": None,
            "service_run_id": run_model.id,
        }
    )


def _format_agent_status_message(
    message: Optional[str],
    default: str = "Server agent failed",
) -> str:
    if message is None or not message.strip():
        return default
    one_line_message = " ".join(message.split())
    if len(one_line_message) <= _MAX_AGENT_STATUS_MESSAGE_CHARS:
        return one_line_message
    return one_line_message[: _MAX_AGENT_STATUS_MESSAGE_CHARS - 3].rstrip() + "..."


async def _record_endpoint_run_submission(endpoint_id: uuid.UUID, run_id: uuid.UUID) -> None:
    async with get_session_ctx() as session:
        await record_endpoint_run_submission(
            session=session,
            endpoint_id=endpoint_id,
            run_id=run_id,
        )
        await session.commit()


async def _record_agent_submitted_runs(
    *,
    endpoint_model: EndpointModel,
    submitted_run_ids: Sequence[uuid.UUID],
    submitted_run_names: Sequence[str],
) -> None:
    valid_submitted_run_names = [
        run_name
        for run_name in submitted_run_names
        if _is_valid_agent_submission_run_name(endpoint_model.name, run_name)
    ]
    if len(submitted_run_ids) == 0 and len(valid_submitted_run_names) == 0:
        return
    async with get_session_ctx() as session:
        res = await session.execute(
            select(RunModel).where(
                or_(
                    RunModel.id.in_(submitted_run_ids),
                    RunModel.run_name.in_(valid_submitted_run_names),
                ),
                RunModel.project_id == endpoint_model.project_id,
                RunModel.user_id == endpoint_model.user_id,
                RunModel.deleted == False,
            )
        )
        runs_by_id = {run.id: run for run in res.scalars().all()}
        runs_by_name = {run.run_name: run for run in runs_by_id.values()}
        for run_id in submitted_run_ids:
            if run_id not in runs_by_id:
                logger.info(
                    "Ignoring endpoint %s submitted run %s because it is not a live run "
                    "owned by the endpoint user/project",
                    endpoint_model.name,
                    run_id,
                )
                continue
            try:
                await record_endpoint_run_submission(
                    session=session,
                    endpoint_id=endpoint_model.id,
                    run_id=run_id,
                )
            except ServerClientError as e:
                logger.info(
                    "Ignoring endpoint %s submitted run %s: %s",
                    endpoint_model.name,
                    run_id,
                    e.msg,
                )
        for run_name in valid_submitted_run_names:
            run = runs_by_name.get(run_name)
            if run is None:
                continue
            try:
                await record_endpoint_run_submission(
                    session=session,
                    endpoint_id=endpoint_model.id,
                    run_id=run.id,
                )
            except ServerClientError as e:
                logger.info(
                    "Ignoring endpoint %s submitted run %s: %s",
                    endpoint_model.name,
                    run_name,
                    e.msg,
                )
        await session.commit()


async def _stop_non_final_submitted_runs(
    *,
    endpoint_model: EndpointModel,
    final_run_id: uuid.UUID,
    pipeline_hinter: PipelineHinterProtocol,
) -> None:
    for run_model in await _get_endpoint_unfinished_runs(endpoint_model):
        if run_model.id == final_run_id or run_model.status == RunStatus.TERMINATING:
            continue
        logger.info(
            "Stopping non-final endpoint run %s after endpoint %s verified run %s",
            run_model.run_name,
            endpoint_model.name,
            final_run_id,
        )
        await _stop_backing_run(
            endpoint_model=endpoint_model,
            run_name=run_model.run_name,
            pipeline_hinter=pipeline_hinter,
        )


def _is_valid_agent_submission_run_name(endpoint_name: str, run_name: str) -> bool:
    prefix = f"{endpoint_name}-"
    if not run_name.startswith(prefix):
        return False
    suffix = run_name[len(prefix) :]
    if not suffix.isdecimal():
        return False
    submission_num = int(suffix)
    return submission_num > 0 and str(submission_num) == suffix


async def _process_running_endpoint(endpoint_model: EndpointModel) -> _ProcessResult:
    readiness = _get_backing_service_readiness(endpoint_model)
    if readiness.failed_message is not None:
        return _ProcessResult(
            update_map={
                "status": EndpointStatus.FAILED,
                "status_message": readiness.failed_message,
            }
        )
    if readiness.model_base_url is None or readiness.model_name is None:
        return _ProcessResult()
    return _ProcessResult(update_map={"status_message": None})


async def _process_stopping_endpoint(
    endpoint_model: EndpointModel,
    pipeline_hinter: PipelineHinterProtocol,
) -> _ProcessResult:
    agent_aborted = True
    if endpoint_model.provisioning_method == "agent":
        agent_aborted = await abort_agent_endpoint(endpoint_model)
    run_models = await _get_endpoint_unfinished_runs(endpoint_model)
    if not run_models:
        if not agent_aborted:
            return _ProcessResult()
        return _get_stopped_result()
    for run_model in run_models:
        if run_model.status == RunStatus.TERMINATING:
            continue
        logger.info(
            "Stopping backing run %s before stopping endpoint %s",
            run_model.run_name,
            endpoint_model.name,
        )
        await _stop_backing_run(
            endpoint_model=endpoint_model,
            run_name=run_model.run_name,
            pipeline_hinter=pipeline_hinter,
        )
    return _ProcessResult()


async def _try_save_agent_endpoint_preset(
    endpoint_model: EndpointModel,
) -> None:
    run_model = endpoint_model.service_run
    if run_model is None:
        return
    await _save_agent_endpoint_preset(
        endpoint_model=endpoint_model,
        run_model=run_model,
    )


async def _save_agent_endpoint_preset(
    endpoint_model: EndpointModel,
    run_model: RunModel,
) -> None:
    try:
        preset = build_endpoint_preset_from_run(run_model)
        saved_preset = await get_endpoint_preset_service().save_preset(
            endpoint_model.project.name,
            preset,
            comments=[
                "Generated by dstack endpoint agent.",
                f"endpoint: {endpoint_model.name}",
                f"endpoint_id: {endpoint_model.id}",
                f"run_id: {run_model.id}",
            ],
        )
    except Exception as e:
        logger.warning(
            "Failed to save endpoint preset for endpoint %s: %s",
            endpoint_model.name,
            e,
            exc_info=True,
        )
        return
    recipe_ids = ", ".join(recipe.id for recipe in saved_preset.recipes)
    logger.info(
        "Saved endpoint preset for model %s recipes %s for endpoint %s",
        saved_preset.model,
        recipe_ids,
        endpoint_model.name,
    )


@dataclass(frozen=True)
class _BackingServiceReadiness:
    failed_message: Optional[str] = None
    model_base_url: Optional[str] = None
    model_name: Optional[str] = None


def _get_backing_service_readiness(endpoint_model: EndpointModel) -> _BackingServiceReadiness:
    run_model = endpoint_model.service_run
    if run_model is None:
        return _BackingServiceReadiness(failed_message="Backing service run is missing")
    return _get_service_run_readiness(run_model, endpoint_name=endpoint_model.name)


def _get_service_run_readiness(
    run_model: RunModel,
    *,
    endpoint_name: str,
) -> _BackingServiceReadiness:
    if run_model.deleted:
        return _BackingServiceReadiness(failed_message="Backing service run was deleted")
    if run_model.status.is_finished():
        return _BackingServiceReadiness(
            failed_message=f"Backing service run finished with status {run_model.status.value}"
        )
    if run_model.status != RunStatus.RUNNING:
        return _BackingServiceReadiness()
    if not _has_registered_running_job(run_model):
        return _BackingServiceReadiness()
    if run_model.service_spec is None:
        return _BackingServiceReadiness()
    try:
        service_spec = ServiceSpec.__response__.parse_raw(run_model.service_spec)
    except ValidationError:
        logger.warning("Endpoint %s backing service spec is invalid", endpoint_name)
        return _BackingServiceReadiness(failed_message="Backing service spec is invalid")
    if service_spec.model is None:
        return _BackingServiceReadiness()
    return _BackingServiceReadiness(
        model_base_url=service_spec.model.base_url,
        model_name=service_spec.model.name,
    )


def _has_registered_running_job(run_model: RunModel) -> bool:
    return any(job.status == JobStatus.RUNNING and job.registered for job in run_model.jobs)


async def _submit_endpoint_from_preset(
    endpoint_id: uuid.UUID,
    pipeline_hinter: PipelineHinterProtocol,
) -> _PresetSubmissionResult:
    async with get_session_ctx() as session:
        res = await session.execute(
            select(EndpointModel)
            .where(
                EndpointModel.id == endpoint_id,
                EndpointModel.status == EndpointStatus.SUBMITTED,
            )
            .options(joinedload(EndpointModel.project).joinedload(ProjectModel.backends))
            .options(joinedload(EndpointModel.user))
        )
        endpoint_model = res.unique().scalar_one_or_none()
        if endpoint_model is None:
            return _PresetSubmissionResult()
        endpoint_configuration = get_endpoint_configuration(endpoint_model)
        if endpoint_configuration.preset_policy == EndpointPresetPolicy.CREATE:
            return _PresetSubmissionResult()
        preset_planning_result = await find_preset_planning_result(
            session=session,
            project=endpoint_model.project,
            user=endpoint_model.user,
            endpoint_name=endpoint_model.name,
            endpoint_configuration=endpoint_configuration,
        )
        preset_plan = preset_planning_result.provisionable
        if preset_plan is None:
            unprovisionable_preset = None
            if preset_planning_result.unprovisionable is not None:
                unprovisionable_preset = _format_preset_plan_label(
                    preset_planning_result.unprovisionable
                )
            return _PresetSubmissionResult(unprovisionable_preset=unprovisionable_preset)
        conflict_message = await _get_active_run_name_conflict_message(
            session=session,
            project=endpoint_model.project,
            run_name=preset_plan.run_plan.run_spec.run_name,
            linked_run_id=endpoint_model.service_run_id,
        )
        if conflict_message is not None:
            raise ServerClientError(conflict_message)
        run = await runs_services.apply_plan(
            session=session,
            user=endpoint_model.user,
            project=endpoint_model.project,
            plan=ApplyRunPlanInput(
                run_spec=preset_plan.run_plan.run_spec,
                current_resource=preset_plan.run_plan.current_resource,
            ),
            force=False,
            pipeline_hinter=pipeline_hinter,
        )
        await record_endpoint_run_submission(
            session=session,
            endpoint_id=endpoint_model.id,
            run_id=run.id,
        )
        await session.commit()
        return _PresetSubmissionResult(
            submission=_PresetSubmission(
                run_id=run.id,
                preset_model=preset_plan.preset.model,
                recipe_id=preset_plan.recipe.id,
            )
        )


async def _get_active_run_name_conflict_message(
    *,
    session,
    project: ProjectModel,
    run_name: Optional[str],
    linked_run_id: Optional[uuid.UUID],
) -> Optional[str]:
    if run_name is None:
        return None
    run_model = await runs_services.get_run_model_by_name(
        session=session,
        project=project,
        run_name=run_name,
    )
    if run_model is None:
        return None
    if linked_run_id == run_model.id:
        return None
    if run_model.status.is_finished():
        return None
    return f"Run name '{run_name}' is taken by an existing run"


def _get_no_provisioning_path_message(
    endpoint_model: EndpointModel,
    unprovisionable_preset: Optional[str] = None,
) -> str:
    endpoint_configuration = get_endpoint_configuration(endpoint_model)
    if unprovisionable_preset is not None:
        reason = f"Endpoint preset {unprovisionable_preset} matched but has no available offers."
        if endpoint_configuration.preset_policy == EndpointPresetPolicy.REUSE:
            return reason
        if get_agent_service().is_enabled() and not can_use_endpoint_agent(
            user=endpoint_model.user,
            project=endpoint_model.project,
        ):
            return f"{reason} {get_endpoint_agent_admin_required_message()}"
        agent_unavailable_reason = get_agent_unavailable_reason()
        if endpoint_configuration.preset_policy == EndpointPresetPolicy.REUSE_OR_CREATE:
            return (
                f"{reason} Creating a preset requires the server agent, "
                f"but {agent_unavailable_reason}"
            )
    if endpoint_configuration.preset_policy == EndpointPresetPolicy.REUSE:
        return _NO_MATCHING_PRESET_MESSAGE
    if get_agent_service().is_enabled() and not can_use_endpoint_agent(
        user=endpoint_model.user,
        project=endpoint_model.project,
    ):
        if endpoint_configuration.preset_policy == EndpointPresetPolicy.REUSE_OR_CREATE:
            return (
                "No matching endpoint presets found. "
                f"{get_endpoint_agent_admin_required_message()}"
            )
        return get_endpoint_agent_admin_required_message()
    agent_unavailable_reason = get_agent_unavailable_reason()
    if endpoint_configuration.preset_policy == EndpointPresetPolicy.REUSE_OR_CREATE:
        return (
            "No matching endpoint presets found. "
            f"Creating a preset requires the server agent, but {agent_unavailable_reason}"
        )
    return f"Preset policy create requires the server agent, but {agent_unavailable_reason}"


def _format_preset_plan_label(preset_plan) -> str:
    return f"for model {preset_plan.preset.model} recipe {preset_plan.recipe.id}"


async def _stop_backing_run(
    endpoint_model: EndpointModel,
    run_name: str,
    pipeline_hinter: PipelineHinterProtocol,
) -> None:
    async with get_session_ctx() as session:
        await runs_services.stop_runs(
            session=session,
            user=endpoint_model.user,
            project=endpoint_model.project,
            runs_names=[run_name],
            abort=False,
            pipeline_hinter=pipeline_hinter,
        )


def _get_stopped_result() -> _ProcessResult:
    return _ProcessResult(
        update_map={
            "status": EndpointStatus.STOPPED,
            "status_message": None,
        }
    )
