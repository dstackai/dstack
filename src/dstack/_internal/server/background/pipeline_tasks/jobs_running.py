import asyncio
import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Iterable, Literal, Optional, Sequence, Union

import httpx
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, contains_eager, joinedload, load_only

from dstack._internal.core.consts import DSTACK_RUNNER_HTTP_PORT, DSTACK_SHIM_HTTP_PORT
from dstack._internal.core.errors import GatewayError, SSHError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import NetworkMode, RegistryAuth
from dstack._internal.core.models.configurations import DevEnvironmentConfiguration
from dstack._internal.core.models.files import FileArchiveMapping
from dstack._internal.core.models.instances import InstanceStatus, SSHConnectionParams
from dstack._internal.core.models.metrics import Metric
from dstack._internal.core.models.profiles import StartupOrder
from dstack._internal.core.models.repos import RemoteRepoCreds
from dstack._internal.core.models.runs import (
    ClusterInfo,
    Job,
    JobProvisioningData,
    JobRuntimeData,
    JobSpec,
    JobStatus,
    JobSubmission,
    JobTerminationReason,
    Run,
    RunSpec,
    RunStatus,
)
from dstack._internal.core.models.volumes import InstanceMountPoint, Volume, VolumeMountPoint
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
from dstack._internal.server.background.scheduled_tasks.common import get_provisioning_timeout
from dstack._internal.server.db import get_db, get_session_ctx
from dstack._internal.server.models import (
    FleetModel,
    InstanceModel,
    JobModel,
    ProbeModel,
    ProjectModel,
    RepoModel,
    RunModel,
    UserModel,
)
from dstack._internal.server.schemas.runner import TaskStatus
from dstack._internal.server.services import events
from dstack._internal.server.services import files as files_services
from dstack._internal.server.services import logs as logs_services
from dstack._internal.server.services.backends.provisioning import (
    get_instance_specific_gpu_devices,
    get_instance_specific_mounts,
    resolve_provisioning_image_name,
)
from dstack._internal.server.services.gateways import get_or_add_gateway_connection
from dstack._internal.server.services.instances import (
    get_instance_remote_connection_info,
    get_instance_ssh_private_keys,
)
from dstack._internal.server.services.jobs import (
    emit_job_status_change_event,
    find_job,
    get_job_attached_volumes,
    get_job_runtime_data,
    get_job_spec,
    is_master_job,
    job_model_to_job_submission,
)
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.services.logging import fmt
from dstack._internal.server.services.metrics import get_job_metrics
from dstack._internal.server.services.repos import (
    get_code_model,
    get_repo_creds,
    repo_model_to_repo_head_with_creds,
)
from dstack._internal.server.services.runner import client
from dstack._internal.server.services.runner.ssh import runner_ssh_tunnel
from dstack._internal.server.services.runs import is_job_ready, run_model_to_run
from dstack._internal.server.services.secrets import get_project_secrets_mapping
from dstack._internal.server.services.storage import get_default_storage
from dstack._internal.server.utils import sentry_utils
from dstack._internal.utils.common import get_current_datetime, get_or_error, run_async
from dstack._internal.utils.interpolator import InterpolatorError, VariablesInterpolator
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


JOB_DISCONNECTED_RETRY_TIMEOUT = timedelta(minutes=2)
"""`The minimum time before terminating active job in case of connectivity issues."""


@dataclass
class JobRunningPipelineItem(PipelineItem):
    status: JobStatus
    replica_num: int


class JobRunningPipeline(Pipeline[JobRunningPipelineItem]):
    def __init__(
        self,
        workers_num: int = 20,
        queue_lower_limit_factor: float = 0.5,
        queue_upper_limit_factor: float = 2.0,
        min_processing_interval: timedelta = timedelta(seconds=5),
        lock_timeout: timedelta = timedelta(seconds=30),
        heartbeat_trigger: timedelta = timedelta(seconds=15),
    ) -> None:
        super().__init__(
            workers_num=workers_num,
            queue_lower_limit_factor=queue_lower_limit_factor,
            queue_upper_limit_factor=queue_upper_limit_factor,
            min_processing_interval=min_processing_interval,
            lock_timeout=lock_timeout,
            heartbeat_trigger=heartbeat_trigger,
        )
        self.__heartbeater = Heartbeater[JobRunningPipelineItem](
            model_type=JobModel,
            lock_timeout=self._lock_timeout,
            heartbeat_trigger=self._heartbeat_trigger,
        )
        self.__fetcher = JobRunningFetcher(
            queue=self._queue,
            queue_desired_minsize=self._queue_desired_minsize,
            min_processing_interval=self._min_processing_interval,
            lock_timeout=self._lock_timeout,
            heartbeater=self._heartbeater,
        )
        self.__workers = [
            JobRunningWorker(queue=self._queue, heartbeater=self._heartbeater)
            for _ in range(self._workers_num)
        ]

    @property
    def hint_fetch_model_name(self) -> str:
        return JobModel.__name__

    @property
    def _heartbeater(self) -> Heartbeater[JobRunningPipelineItem]:
        return self.__heartbeater

    @property
    def _fetcher(self) -> Fetcher[JobRunningPipelineItem]:
        return self.__fetcher

    @property
    def _workers(self) -> Sequence["JobRunningWorker"]:
        return self.__workers


class JobRunningFetcher(Fetcher[JobRunningPipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[JobRunningPipelineItem],
        queue_desired_minsize: int,
        min_processing_interval: timedelta,
        lock_timeout: timedelta,
        heartbeater: Heartbeater[JobRunningPipelineItem],
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

    @sentry_utils.instrument_named_task("pipeline_tasks.JobRunningFetcher.fetch")
    async def fetch(self, limit: int) -> list[JobRunningPipelineItem]:
        job_lock, _ = get_locker(get_db().dialect_name).get_lockset(JobModel.__tablename__)
        async with job_lock:
            async with get_session_ctx() as session:
                now = get_current_datetime()
                res = await session.execute(
                    select(JobModel)
                    .join(JobModel.run)
                    .where(
                        JobModel.status.in_(
                            [JobStatus.PROVISIONING, JobStatus.PULLING, JobStatus.RUNNING]
                        ),
                        RunModel.status.not_in([RunStatus.TERMINATING]),
                        or_(
                            # Process provisioning and pulling jobs quicker for low-latency provisioning.
                            # Active jobs processing can be less frequent to minimize contention with `RunPipeline`.
                            and_(
                                JobModel.status.in_([JobStatus.PROVISIONING, JobStatus.PULLING]),
                                JobModel.last_processed_at <= now - self._min_processing_interval,
                            ),
                            and_(
                                JobModel.status.in_([JobStatus.RUNNING]),
                                JobModel.last_processed_at
                                <= now - self._min_processing_interval * 2,
                            ),
                        ),
                        or_(
                            and_(
                                # Do not try to lock jobs if the run is waiting for the lock,
                                # but allow retrying jobs whose own lock is stale because
                                # the run pipeline cannot reclaim stale job locks.
                                RunModel.lock_owner.is_(None),
                                JobModel.lock_expires_at.is_(None),
                            ),
                            JobModel.lock_expires_at < now,
                        ),
                        or_(
                            JobModel.lock_owner.is_(None),
                            JobModel.lock_owner == JobRunningPipeline.__name__,
                        ),
                    )
                    .order_by(JobModel.last_processed_at.asc())
                    .limit(limit)
                    .with_for_update(skip_locked=True, key_share=True, of=JobModel)
                    .options(
                        load_only(
                            JobModel.id,
                            JobModel.lock_token,
                            JobModel.lock_expires_at,
                            JobModel.status,
                            JobModel.replica_num,
                        )
                    )
                )
                job_models = list(res.scalars().all())
                lock_expires_at = get_current_datetime() + self._lock_timeout
                lock_token = uuid.uuid4()
                items = []
                for job_model in job_models:
                    prev_lock_expired = job_model.lock_expires_at is not None
                    job_model.lock_expires_at = lock_expires_at
                    job_model.lock_token = lock_token
                    job_model.lock_owner = JobRunningPipeline.__name__
                    items.append(
                        JobRunningPipelineItem(
                            __tablename__=JobModel.__tablename__,
                            id=job_model.id,
                            lock_expires_at=lock_expires_at,
                            lock_token=lock_token,
                            prev_lock_expired=prev_lock_expired,
                            status=job_model.status,
                            replica_num=job_model.replica_num,
                        )
                    )
                await session.commit()
        return items


class JobRunningWorker(Worker[JobRunningPipelineItem]):
    def __init__(
        self,
        queue: asyncio.Queue[JobRunningPipelineItem],
        heartbeater: Heartbeater[JobRunningPipelineItem],
    ) -> None:
        super().__init__(
            queue=queue,
            heartbeater=heartbeater,
        )

    @sentry_utils.instrument_named_task("pipeline_tasks.JobRunningWorker.process")
    async def process(self, item: JobRunningPipelineItem):
        context = await _load_process_context(item=item)
        if context is None:
            log_lock_token_mismatch(logger, item)
            return

        result = await _process_running_job(context=context)
        await _apply_process_result(
            item=item,
            job_model=context.job_model,
            result=result,
        )


@dataclass
class _ProcessContext:
    job_model: JobModel
    run_model: RunModel
    run: Run
    job: Job
    job_submission: JobSubmission
    job_provisioning_data: Optional[JobProvisioningData]
    server_ssh_private_keys: Optional[tuple[str, Optional[str]]] = None

    @property
    def repo_model(self) -> RepoModel:
        return self.run_model.repo

    @property
    def project(self) -> ProjectModel:
        return self.run_model.project


class _JobUpdateMap(ItemUpdateMap, total=False):
    status: JobStatus
    termination_reason: Optional[JobTerminationReason]
    termination_reason_message: Optional[str]
    job_provisioning_data: Optional[str]
    job_runtime_data: Optional[str]
    runner_timestamp: Optional[int]
    disconnected_at: Optional[datetime]
    inactivity_secs: Optional[int]
    exit_status: Optional[int]
    registered: bool


@dataclass
class _RegisterReplicaResult:
    gateway_target: Optional[events.Target]  # None = no gateway


@dataclass
class _ProcessResult:
    job_update_map: _JobUpdateMap = field(default_factory=_JobUpdateMap)
    new_probe_models: list[ProbeModel] = field(default_factory=list)
    replica_registration: Optional[_RegisterReplicaResult] = None  # None = not registered yet


@dataclass
class _StartupContext:
    cluster_info: ClusterInfo
    volumes: list[Volume]
    secrets: dict[str, str]
    repo_creds: Optional[RemoteRepoCreds]


async def _load_process_context(item: JobRunningPipelineItem) -> Optional[_ProcessContext]:
    async with get_session_ctx() as session:
        job_model = await _refetch_locked_job_model(session=session, item=item)
        if job_model is None:
            return None
        if item.status == JobStatus.RUNNING:
            # RUNNING jobs don't access run.jobs — skip loading sibling jobs entirely.
            run_model = await _fetch_run_model(session=session, run_id=job_model.run_id)
            run = run_model_to_run(run_model, include_sensitive=True, include_jobs=False)
            job = Job(
                job_spec=get_job_spec(job_model),
                job_submissions=[job_model_to_job_submission(job_model)],
            )
        else:
            # PROVISIONING/PULLING jobs need same-replica siblings for cluster coordination.
            # All sibling access is replica-scoped, so only load jobs for this replica.
            run_model = await _fetch_run_model(
                session=session, run_id=job_model.run_id, replica_num=item.replica_num
            )
            run = run_model_to_run(run_model, include_sensitive=True)
            job = find_job(run.jobs, job_model.replica_num, job_model.job_num)
        job_submission = job_model_to_job_submission(job_model)
        server_ssh_private_keys = get_instance_ssh_private_keys(get_or_error(job_model.instance))
        return _ProcessContext(
            job_model=job_model,
            run_model=run_model,
            run=run,
            job=job,
            job_submission=job_submission,
            job_provisioning_data=job_submission.job_provisioning_data,
            server_ssh_private_keys=server_ssh_private_keys,
        )


async def _process_running_job(context: _ProcessContext) -> _ProcessResult:
    result = _ProcessResult()
    if context.job_provisioning_data is None:
        logger.error("%s: job_provisioning_data of an active job is None", fmt(context.job_model))
        _terminate_job(
            job_model=context.job_model,
            job_update_map=result.job_update_map,
            termination_reason=JobTerminationReason.TERMINATED_BY_SERVER,
            termination_reason_message=(
                "Unexpected server error: job_provisioning_data of an active job is None"
            ),
        )
        return result

    if context.job_model.status == JobStatus.PROVISIONING:
        startup_context = await _prepare_startup_context(context=context, result=result)
        if startup_context is None:
            return result
        await _process_provisioning_status(
            context=context, startup_context=startup_context, result=result
        )
    elif context.job_model.status == JobStatus.PULLING:
        startup_context = await _prepare_startup_context(context=context, result=result)
        if startup_context is None:
            return result
        await _process_pulling_status(
            context=context, startup_context=startup_context, result=result
        )
    elif context.job_model.status == JobStatus.RUNNING:
        await _process_running_status(context=context, result=result)

    if _get_result_status(context.job_model, result) == JobStatus.RUNNING:
        if context.job_model.status != JobStatus.RUNNING:
            _initialize_running_job_probes(
                job_model=context.job_model,
                job=context.job,
                result=result,
            )
        await _maybe_register_replica(context=context, result=result)
        await _check_gpu_utilization(context=context, result=result)
    return result


async def _prepare_startup_context(
    context: _ProcessContext,
    result: _ProcessResult,
) -> Optional[_StartupContext]:
    job_provisioning_data = get_or_error(context.job_provisioning_data)

    for other_job in context.run.jobs:
        if (
            other_job.job_spec.replica_num == context.job.job_spec.replica_num
            and other_job.job_submissions[-1].status == JobStatus.SUBMITTED
        ):
            logger.debug(
                "%s: waiting for all jobs in the replica to be provisioned",
                fmt(context.job_model),
            )
            return None

    cluster_info = _get_cluster_info(
        jobs=context.run.jobs,
        replica_num=context.job.job_spec.replica_num,
        job_provisioning_data=job_provisioning_data,
        job_runtime_data=context.job_submission.job_runtime_data,
    )

    async with get_session_ctx() as session:
        volumes = await get_job_attached_volumes(
            session=session,
            project=context.project,
            run_spec=context.run.run_spec,
            job_num=context.job.job_spec.job_num,
            job_provisioning_data=job_provisioning_data,
        )
        repo_creds_model = await get_repo_creds(
            session=session,
            repo=context.repo_model,
            user=context.run_model.user,
        )
        secrets = await get_project_secrets_mapping(session=session, project=context.project)

    repo_creds = repo_model_to_repo_head_with_creds(
        context.repo_model,
        repo_creds_model,
    ).repo_creds

    try:
        _interpolate_secrets(secrets, context.job.job_spec)
    except InterpolatorError as e:
        _terminate_job(
            job_model=context.job_model,
            job_update_map=result.job_update_map,
            termination_reason=JobTerminationReason.TERMINATED_BY_SERVER,
            termination_reason_message=f"Secrets interpolation error: {e.args[0]}",
        )
        return None

    return _StartupContext(
        cluster_info=cluster_info,
        volumes=volumes,
        secrets=secrets,
        repo_creds=repo_creds,
    )


async def _refetch_locked_job_model(
    session: AsyncSession, item: JobRunningPipelineItem
) -> Optional[JobModel]:
    res = await session.execute(
        select(JobModel)
        .where(
            JobModel.id == item.id,
            JobModel.lock_token == item.lock_token,
        )
        .options(joinedload(JobModel.instance).joinedload(InstanceModel.project))
        .options(joinedload(JobModel.probes).load_only(ProbeModel.success_streak))
        .execution_options(populate_existing=True)
    )
    return res.unique().scalar_one_or_none()


async def _fetch_run_model(
    session: AsyncSession,
    run_id: uuid.UUID,
    replica_num: Optional[int] = None,
) -> RunModel:
    """Fetch run model with related project, user, repo, and fleet.

    Args:
        replica_num: If None, skip loading jobs (for RUNNING jobs that don't need siblings).
            If set, load only latest-submission jobs for that replica (for PROVISIONING/PULLING
            jobs that need same-replica siblings for cluster coordination).
    """
    query = (
        select(RunModel)
        .where(RunModel.id == run_id)
        .options(joinedload(RunModel.project))
        .options(joinedload(RunModel.user))
        .options(joinedload(RunModel.repo))
        .options(joinedload(RunModel.fleet).load_only(FleetModel.id, FleetModel.name))
    )
    if replica_num is not None:
        latest_submissions_sq = (
            select(
                JobModel.run_id.label("run_id"),
                JobModel.replica_num.label("replica_num"),
                JobModel.job_num.label("job_num"),
                func.max(JobModel.submission_num).label("max_submission_num"),
            )
            .where(JobModel.run_id == run_id, JobModel.replica_num == replica_num)
            .group_by(JobModel.run_id, JobModel.replica_num, JobModel.job_num)
            .subquery()
        )
        job_alias = aliased(JobModel)
        query = (
            query.join(job_alias, job_alias.run_id == RunModel.id)
            .join(
                latest_submissions_sq,
                onclause=and_(
                    job_alias.run_id == latest_submissions_sq.c.run_id,
                    job_alias.replica_num == latest_submissions_sq.c.replica_num,
                    job_alias.job_num == latest_submissions_sq.c.job_num,
                    job_alias.submission_num == latest_submissions_sq.c.max_submission_num,
                ),
            )
            .options(contains_eager(RunModel.jobs, alias=job_alias))
        )
    res = await session.execute(query)
    return res.unique().scalar_one()


async def _process_provisioning_status(
    context: _ProcessContext,
    startup_context: _StartupContext,
    result: _ProcessResult,
) -> None:
    job_provisioning_data = get_or_error(context.job_provisioning_data)
    server_ssh_private_keys = get_or_error(context.server_ssh_private_keys)

    if job_provisioning_data.hostname is None:
        _wait_for_instance_provisioning_data(context.job_model, result)
        return
    if _should_wait_for_other_nodes(context.run, context.job, context.job_model):
        return

    if job_provisioning_data.dockerized:
        logger.debug(
            "%s: process provisioning job with shim, age=%s",
            fmt(context.job_model),
            context.job_submission.age,
        )
        ssh_user = job_provisioning_data.username
        assert context.run.run_spec.ssh_key_pub is not None
        user_ssh_key = context.run.run_spec.ssh_key_pub.strip()
        public_keys = [context.project.ssh_public_key.strip(), user_ssh_key]
        if job_provisioning_data.backend == BackendType.LOCAL:
            user_ssh_key = ""
        success = await run_async(
            _process_provisioning_with_shim,
            server_ssh_private_keys,
            job_provisioning_data,
            None,
            run=context.run,
            job_model=context.job_model,
            jrd=get_job_runtime_data(context.job_model),
            jpd=job_provisioning_data,
            volumes=startup_context.volumes,
            registry_auth=context.job.job_spec.registry_auth,
            public_keys=public_keys,
            ssh_user=ssh_user,
            ssh_key=user_ssh_key,
        )
        if success:
            _set_job_status(context.job_model, result, JobStatus.PULLING)
            return
    else:
        logger.debug(
            "%s: process provisioning job without shim, age=%s",
            fmt(context.job_model),
            context.job_submission.age,
        )
        runner_availability = await run_async(
            _get_runner_availability,
            server_ssh_private_keys,
            job_provisioning_data,
            None,
        )
        if runner_availability == _RunnerAvailability.AVAILABLE:
            file_archives = await _get_job_file_archives(
                archive_mappings=context.job.job_spec.file_archives,
                user=context.run_model.user,
            )
            code = await _get_job_code(
                project=context.project,
                repo=context.repo_model,
                code_hash=_get_repo_code_hash(context.run, context.job),
            )
            submit_result = await run_async(
                _submit_job_to_runner,
                server_ssh_private_keys,
                job_provisioning_data,
                None,
                run=context.run,
                job_model=context.job_model,
                job=context.job,
                jrd=get_job_runtime_data(context.job_model),
                cluster_info=startup_context.cluster_info,
                code=code,
                file_archives=file_archives,
                secrets=startup_context.secrets,
                repo_credentials=startup_context.repo_creds,
                success_if_not_available=False,
            )
            if submit_result is not False:
                _apply_submit_job_to_runner_result(
                    job_model=context.job_model,
                    result=result,
                    submit_result=submit_result,
                )
            if submit_result is not False and submit_result.success:
                return

    provisioning_timeout = get_provisioning_timeout(
        backend_type=job_provisioning_data.get_base_backend(),
        instance_type_name=job_provisioning_data.instance_type.name,
    )
    if context.job_submission.age > provisioning_timeout:
        _terminate_job(
            job_model=context.job_model,
            job_update_map=result.job_update_map,
            termination_reason=JobTerminationReason.WAITING_RUNNER_LIMIT_EXCEEDED,
            termination_reason_message=(
                f"Runner did not become available within {provisioning_timeout.total_seconds()}s."
                f" Job submission age: {context.job_submission.age.total_seconds()}s)"
            ),
        )


async def _process_pulling_status(
    context: _ProcessContext,
    startup_context: _StartupContext,
    result: _ProcessResult,
) -> None:
    job_provisioning_data = get_or_error(context.job_provisioning_data)
    server_ssh_private_keys = get_or_error(context.server_ssh_private_keys)

    logger.debug(
        "%s: process pulling job with shim, age=%s",
        fmt(context.job_model),
        context.job_submission.age,
    )
    shim_state = await run_async(
        _sync_shim_pulling_state,
        server_ssh_private_keys,
        job_provisioning_data,
        None,
        job_model=context.job_model,
        jrd=_get_result_job_runtime_data(context.job_model, result),
    )
    if shim_state is not False:
        if shim_state.job_runtime_data is not None:
            _set_job_runtime_data(result, shim_state.job_runtime_data)

        if shim_state.state == _ShimPullingState.WAITING:
            _reset_disconnected_at(context.job_model, result)
            return

        if shim_state.state == _ShimPullingState.FAILED:
            logger.warning(
                "%s: failed due to %s, age=%s",
                fmt(context.job_model),
                get_or_error(shim_state.termination_reason).value,
                context.job_submission.age,
            )
            _terminate_job(
                job_model=context.job_model,
                job_update_map=result.job_update_map,
                termination_reason=get_or_error(shim_state.termination_reason),
                termination_reason_message=get_or_error(shim_state.termination_reason_message),
            )
            return

        # _ShimPullingState.READY
        job_runtime_data = _get_result_job_runtime_data(context.job_model, result)
        runner_availability = await run_async(
            _get_runner_availability,
            server_ssh_private_keys,
            job_provisioning_data,
            job_runtime_data,
        )
        if runner_availability == _RunnerAvailability.UNAVAILABLE:
            _reset_disconnected_at(context.job_model, result)
            return

        if runner_availability == _RunnerAvailability.AVAILABLE:
            file_archives = await _get_job_file_archives(
                archive_mappings=context.job.job_spec.file_archives,
                user=context.run_model.user,
            )
            code = await _get_job_code(
                project=context.project,
                repo=context.repo_model,
                code_hash=_get_repo_code_hash(context.run, context.job),
            )
            submit_result = await run_async(
                _submit_job_to_runner,
                server_ssh_private_keys,
                job_provisioning_data,
                job_runtime_data,
                run=context.run,
                job_model=context.job_model,
                job=context.job,
                jrd=job_runtime_data,
                cluster_info=startup_context.cluster_info,
                code=code,
                file_archives=file_archives,
                secrets=startup_context.secrets,
                repo_credentials=startup_context.repo_creds,
                success_if_not_available=True,
            )
            if submit_result is not False:
                _apply_submit_job_to_runner_result(
                    job_model=context.job_model,
                    result=result,
                    submit_result=submit_result,
                )
            if submit_result is not False and submit_result.success:
                _reset_disconnected_at(context.job_model, result)
                return

    # SSH tunnel failed or READY but runner submit failed — treat as disconnect
    _handle_instance_unreachable(context, result, job_provisioning_data)


async def _process_running_status(
    context: _ProcessContext,
    result: _ProcessResult,
) -> None:
    job_provisioning_data = get_or_error(context.job_provisioning_data)
    server_ssh_private_keys = get_or_error(context.server_ssh_private_keys)

    logger.debug(
        "%s: process running job, age=%s",
        fmt(context.job_model),
        context.job_submission.age,
    )
    process_running_result = await run_async(
        _process_running,
        server_ssh_private_keys,
        job_provisioning_data,
        context.job_submission.job_runtime_data,
        run_model=context.run_model,
        job_model=context.job_model,
    )
    if process_running_result is not False:
        result.job_update_map.update(process_running_result.job_update_map)
        _reset_disconnected_at(context.job_model, result)
        return

    _handle_instance_unreachable(context, result, job_provisioning_data)


async def _apply_process_result(
    item: JobRunningPipelineItem,
    job_model: JobModel,
    result: _ProcessResult,
) -> None:
    set_processed_update_map_fields(result.job_update_map)
    set_unlock_update_map_fields(result.job_update_map)

    async with get_session_ctx() as session:
        now = get_current_datetime()
        resolve_now_placeholders(result.job_update_map, now=now)
        res = await session.execute(
            update(JobModel)
            .where(
                JobModel.id == item.id,
                JobModel.lock_token == item.lock_token,
            )
            .values(**result.job_update_map)
            .returning(JobModel.id)
        )
        updated_ids = list(res.scalars().all())
        if len(updated_ids) == 0:
            log_lock_token_changed_after_processing(logger, item)
            return

        if result.new_probe_models:
            session.add_all(result.new_probe_models)

        _emit_result_events(session=session, job_model=job_model, result=result)


def _emit_result_events(
    session: AsyncSession,
    job_model: JobModel,
    result: _ProcessResult,
) -> None:
    """Emit audit events for changes recorded in result.."""
    emit_job_status_change_event(
        session=session,
        job_model=job_model,
        old_status=job_model.status,
        new_status=result.job_update_map.get("status", job_model.status),
        termination_reason=result.job_update_map.get(
            "termination_reason", job_model.termination_reason
        ),
        termination_reason_message=result.job_update_map.get(
            "termination_reason_message",
            job_model.termination_reason_message,
        ),
    )
    _emit_reachability_change_event(
        session=session,
        job_model=job_model,
        old_disconnected_at=job_model.disconnected_at,
        new_disconnected_at=result.job_update_map.get(
            "disconnected_at",
            job_model.disconnected_at,
        ),
    )
    if result.replica_registration is not None:
        targets = [events.Target.from_model(job_model)]
        if result.replica_registration.gateway_target is not None:
            targets.append(result.replica_registration.gateway_target)
        events.emit(
            session,
            "Service replica registered to receive requests",
            actor=events.SystemActor(),
            targets=targets,
        )


def _wait_for_instance_provisioning_data(
    job_model: JobModel,
    result: _ProcessResult,
) -> None:
    if job_model.instance is None:
        logger.error(
            "%s: cannot update job_provisioning_data. job_model.instance is None.",
            fmt(job_model),
        )
        return
    if job_model.instance.job_provisioning_data is None:
        logger.error(
            "%s: cannot update job_provisioning_data. job_model.job_provisioning_data is None.",
            fmt(job_model),
        )
        return

    if job_model.instance.status == InstanceStatus.TERMINATED:
        _terminate_job(
            job_model=job_model,
            job_update_map=result.job_update_map,
            termination_reason=JobTerminationReason.WAITING_INSTANCE_LIMIT_EXCEEDED,
            termination_reason_message="Instance is terminated",
        )
        return

    result.job_update_map["job_provisioning_data"] = job_model.instance.job_provisioning_data


def _handle_instance_unreachable(
    context: _ProcessContext,
    result: _ProcessResult,
    job_provisioning_data: JobProvisioningData,
) -> None:
    _set_disconnected_at_now(context.job_model, result)
    if not _should_terminate_job_due_to_disconnect(
        _get_result_disconnected_at(context.job_model, result)
    ):
        logger.warning(
            "%s: is unreachable, waiting for the instance to become reachable again, age=%s",
            fmt(context.job_model),
            context.job_submission.age,
        )
        return
    if job_provisioning_data.instance_type.resources.spot:
        termination_reason = JobTerminationReason.INTERRUPTED_BY_NO_CAPACITY
    else:
        termination_reason = JobTerminationReason.INSTANCE_UNREACHABLE
    _terminate_job(
        job_model=context.job_model,
        job_update_map=result.job_update_map,
        termination_reason=termination_reason,
        termination_reason_message="Instance is unreachable",
    )


def _initialize_running_job_probes(
    job_model: JobModel,
    job: Job,
    result: _ProcessResult,
) -> None:
    for probe_num in range(len(job.job_spec.probes)):
        result.new_probe_models.append(
            ProbeModel(
                name=f"{job_model.job_name}-{probe_num}",
                job_id=job_model.id,
                probe_num=probe_num,
                due=get_current_datetime(),
                success_streak=0,
                active=True,
            )
        )


async def _maybe_register_replica(
    context: _ProcessContext,
    result: _ProcessResult,
) -> None:
    if (
        context.run.run_spec.configuration.type != "service"
        or _get_result_registered(context.job_model, result)
        or context.job_model.job_num != 0
        or result.new_probe_models
        or not is_job_ready(context.job_model.probes, context.job.job_spec.probes)
    ):
        return

    ssh_head_proxy: Optional[SSHConnectionParams] = None
    ssh_head_proxy_private_key: Optional[str] = None
    instance = get_or_error(context.job_model.instance)
    rci = get_instance_remote_connection_info(instance)
    if rci is not None and rci.ssh_proxy is not None:
        ssh_head_proxy = rci.ssh_proxy
        ssh_head_proxy_keys = get_or_error(rci.ssh_proxy_keys)
        ssh_head_proxy_private_key = ssh_head_proxy_keys[0].private

    try:
        gateway_target = await _register_service_replica(
            context=context,
            result=result,
            ssh_head_proxy=ssh_head_proxy,
            ssh_head_proxy_private_key=ssh_head_proxy_private_key,
        )
    except GatewayError as e:
        logger.warning("%s: failed to register service replica: %s", fmt(context.job_model), e)
        _terminate_job(
            job_model=context.job_model,
            job_update_map=result.job_update_map,
            termination_reason=JobTerminationReason.GATEWAY_ERROR,
            termination_reason_message="Failed to register service replica",
        )
        return

    result.job_update_map["registered"] = True
    result.replica_registration = _RegisterReplicaResult(gateway_target=gateway_target)


async def _register_service_replica(
    context: _ProcessContext,
    result: _ProcessResult,
    ssh_head_proxy: Optional[SSHConnectionParams],
    ssh_head_proxy_private_key: Optional[str],
) -> Optional[events.Target]:
    if context.run_model.gateway_id is None:
        return None

    async with get_session_ctx() as session:
        gateway_model, conn = await get_or_add_gateway_connection(
            session, context.run_model.gateway_id
        )
    gateway_target = events.Target.from_model(gateway_model)
    assert context.job_model.instance is not None
    instance_project_ssh_private_key = None
    if context.job_model.project_id != context.job_model.instance.project_id:
        instance_project_ssh_private_key = context.job_model.instance.project.ssh_private_key
    # JobRuntimeData might change on PULLING -> RUNNING path
    # so we must update job_submission with the result value.
    job_submission = context.job_submission.copy(deep=True)
    job_submission.job_runtime_data = _get_result_job_runtime_data(context.job_model, result)
    try:
        logger.debug(
            "%s: registering replica for service %s", fmt(context.job_model), context.run.id.hex
        )
        async with conn.client() as gateway_client:
            await gateway_client.register_replica(
                run=context.run,
                job_spec=JobSpec.__response__.parse_raw(context.job_model.job_spec_data),
                job_submission=job_submission,
                instance_project_ssh_private_key=instance_project_ssh_private_key,
                ssh_head_proxy=ssh_head_proxy,
                ssh_head_proxy_private_key=ssh_head_proxy_private_key,
            )
    except (httpx.RequestError, SSHError) as e:
        logger.debug("Gateway request failed", exc_info=True)
        raise GatewayError(repr(e))
    except GatewayError as e:
        if "already exists in service" in e.msg:
            logger.warning(
                (
                    "%s: could not register replica in gateway: %s."
                    " NOTE: if you just updated dstack from pre-0.19.25 to 0.19.25+,"
                    " expect to see this warning once for every running service replica"
                ),
                fmt(context.job_model),
                e.msg,
            )
        else:
            raise
    return gateway_target


async def _check_gpu_utilization(
    context: _ProcessContext,
    result: _ProcessResult,
) -> None:
    policy = context.job.job_spec.utilization_policy
    if policy is None:
        return

    after = get_current_datetime() - timedelta(seconds=policy.time_window)
    async with get_session_ctx() as session:
        job_metrics = await get_job_metrics(session, context.job_model, after=after)
    gpus_util_metrics: list[Metric] = []
    for metric in job_metrics.metrics:
        if metric.name.startswith("gpu_util_percent_gpu"):
            gpus_util_metrics.append(metric)
    if not gpus_util_metrics or gpus_util_metrics[0].timestamps[-1] > after + timedelta(minutes=1):
        logger.debug("%s: GPU utilization check: not enough samples", fmt(context.job_model))
        return
    if _should_terminate_due_to_low_gpu_util(
        policy.min_gpu_utilization, [metric.values for metric in gpus_util_metrics]
    ):
        logger.debug("%s: GPU utilization check: terminating", fmt(context.job_model))
        _terminate_job(
            job_model=context.job_model,
            job_update_map=result.job_update_map,
            termination_reason=JobTerminationReason.TERMINATED_DUE_TO_UTILIZATION_POLICY,
            termination_reason_message=(
                f"The job GPU utilization below {policy.min_gpu_utilization}%"
                f" for {policy.time_window} seconds"
            ),
        )
    else:
        logger.debug("%s: GPU utilization check: OK", fmt(context.job_model))


def _should_terminate_due_to_low_gpu_util(
    min_util: int, gpus_util: Iterable[Iterable[int]]
) -> bool:
    for gpu_util in gpus_util:
        if all(util < min_util for util in gpu_util):
            return True
    return False


def _should_wait_for_other_nodes(run: Run, job: Job, job_model: JobModel) -> bool:
    for other_job in run.jobs:
        if (
            other_job.job_spec.replica_num == job.job_spec.replica_num
            and other_job.job_submissions[-1].status == JobStatus.PROVISIONING
            and other_job.job_submissions[-1].job_provisioning_data is not None
            and other_job.job_submissions[-1].job_provisioning_data.hostname is None
        ):
            logger.debug("%s: waiting for other job to have IP assigned", fmt(job_model))
            return True
    master_job = find_job(run.jobs, job.job_spec.replica_num, 0)
    if (
        job.job_spec.job_num != 0
        and run.run_spec.merged_profile.startup_order == StartupOrder.MASTER_FIRST
        and master_job.job_submissions[-1].status != JobStatus.RUNNING
    ):
        logger.debug("%s: waiting for master job to become running", fmt(job_model))
        return True
    if (
        is_master_job(job)
        and run.run_spec.merged_profile.startup_order == StartupOrder.WORKERS_FIRST
    ):
        for other_job in run.jobs:
            if (
                other_job.job_spec.replica_num == job.job_spec.replica_num
                and other_job.job_spec.job_num != job.job_spec.job_num
                and other_job.job_submissions[-1].status != JobStatus.RUNNING
            ):
                logger.debug("%s: waiting for worker job to become running", fmt(job_model))
                return True
    return False


@runner_ssh_tunnel(ports=[DSTACK_SHIM_HTTP_PORT], retries=1)
def _process_provisioning_with_shim(
    ports: Dict[int, int],
    run: Run,
    job_model: JobModel,
    jrd: Optional[JobRuntimeData],
    jpd: JobProvisioningData,
    volumes: list[Volume],
    registry_auth: Optional[RegistryAuth],
    public_keys: list[str],
    ssh_user: str,
    ssh_key: str,
) -> bool:
    job_spec = JobSpec.__response__.parse_raw(job_model.job_spec_data)
    shim_client = client.ShimClient(port=ports[DSTACK_SHIM_HTTP_PORT])

    resp = shim_client.healthcheck()
    if resp is None:
        logger.debug("%s: shim is not available yet", fmt(job_model))
        return False

    registry_username = ""
    registry_password = ""
    if registry_auth is not None:
        registry_username = registry_auth.username
        registry_password = registry_auth.password

    volume_mounts: list[VolumeMountPoint] = []
    instance_mounts: list[InstanceMountPoint] = []
    for mount in run.run_spec.configuration.volumes:
        if isinstance(mount, VolumeMountPoint):
            volume_mounts.append(mount.copy())
        elif isinstance(mount, InstanceMountPoint):
            instance_mounts.append(mount)
        else:
            assert False, f"unexpected mount point: {mount!r}"

    for volume, volume_mount in zip(volumes, volume_mounts):
        volume_mount.name = volume.name

    instance_mounts += get_instance_specific_mounts(jpd.backend, jpd.instance_type.name)
    gpu_devices = get_instance_specific_gpu_devices(jpd.backend, jpd.instance_type.name)

    container_user = "root"
    if jrd is not None:
        gpu = jrd.gpu
        cpu = jrd.cpu
        memory = jrd.memory
        network_mode = jrd.network_mode
    else:
        gpu = None
        cpu = None
        memory = None
        network_mode = NetworkMode.HOST
    image_name = resolve_provisioning_image_name(job_spec, jpd)
    if shim_client.is_api_v2_supported():
        shim_client.submit_task(
            task_id=job_model.id,
            name=job_model.job_name,
            registry_username=registry_username,
            registry_password=registry_password,
            image_name=image_name,
            container_user=container_user,
            privileged=job_spec.privileged,
            gpu=gpu,
            cpu=cpu,
            memory=memory,
            shm_size=job_spec.requirements.resources.shm_size,
            network_mode=network_mode,
            volumes=volumes,
            volume_mounts=volume_mounts,
            instance_mounts=instance_mounts,
            gpu_devices=gpu_devices,
            host_ssh_user=ssh_user,
            host_ssh_keys=[ssh_key] if ssh_key else [],
            container_ssh_keys=public_keys,
            instance_id=jpd.instance_id,
        )
    else:
        submitted = shim_client.submit(
            username=registry_username,
            password=registry_password,
            image_name=image_name,
            privileged=job_spec.privileged,
            container_name=job_model.job_name,
            container_user=container_user,
            shm_size=job_spec.requirements.resources.shm_size,
            public_keys=public_keys,
            ssh_user=ssh_user,
            ssh_key=ssh_key,
            mounts=volume_mounts,
            volumes=volumes,
            instance_mounts=instance_mounts,
            instance_id=jpd.instance_id,
        )
        if not submitted:
            logger.warning(
                "%s: failed to submit, shim is already running a job, stopping it now, retry later",
                fmt(job_model),
            )
            shim_client.stop(force=True)
            return False

    return True


class _RunnerAvailability(enum.Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class _ShimPullingState(enum.Enum):
    WAITING = "waiting"
    READY = "ready"
    FAILED = "failed"


@dataclass
class _SyncShimPullingStateResult:
    state: _ShimPullingState
    termination_reason: Optional[JobTerminationReason] = None
    termination_reason_message: Optional[str] = None
    job_runtime_data: Optional[JobRuntimeData] = None


@runner_ssh_tunnel(ports=[DSTACK_RUNNER_HTTP_PORT], retries=1)
def _get_runner_availability(ports: Dict[int, int]) -> _RunnerAvailability:
    runner_client = client.RunnerClient(port=ports[DSTACK_RUNNER_HTTP_PORT])
    if runner_client.healthcheck() is None:
        return _RunnerAvailability.UNAVAILABLE
    return _RunnerAvailability.AVAILABLE


@runner_ssh_tunnel(ports=[DSTACK_SHIM_HTTP_PORT])
def _sync_shim_pulling_state(
    ports: Dict[int, int],
    job_model: JobModel,
    jrd: Optional[JobRuntimeData] = None,
) -> Union[_SyncShimPullingStateResult, Literal[False]]:
    shim_client = client.ShimClient(port=ports[DSTACK_SHIM_HTTP_PORT])
    if shim_client.is_api_v2_supported():
        task = shim_client.get_task(job_model.id)
        if task.status == TaskStatus.TERMINATED:
            logger.warning(
                "shim failed to execute job %s: %s (%s)",
                job_model.job_name,
                task.termination_reason,
                task.termination_message,
            )
            logger.debug("task status: %s", task.dict())
            return _SyncShimPullingStateResult(
                state=_ShimPullingState.FAILED,
                termination_reason=JobTerminationReason(task.termination_reason.lower()),
                termination_reason_message=task.termination_message,
            )

        if task.status != TaskStatus.RUNNING:
            return _SyncShimPullingStateResult(state=_ShimPullingState.WAITING)

        if jrd is not None:
            if task.ports is None:
                return _SyncShimPullingStateResult(state=_ShimPullingState.WAITING)
            jrd = jrd.copy(update={"ports": {pm.container: pm.host for pm in task.ports}})
    else:
        shim_status = shim_client.pull()
        if (
            shim_status.state == "pending"
            and shim_status.result is not None
            and shim_status.result.reason != ""
        ):
            logger.warning(
                "shim failed to execute job %s: %s (%s)",
                job_model.job_name,
                shim_status.result.reason,
                shim_status.result.reason_message,
            )
            logger.debug("shim status: %s", shim_status.dict())
            return _SyncShimPullingStateResult(
                state=_ShimPullingState.FAILED,
                termination_reason=JobTerminationReason(shim_status.result.reason.lower()),
                termination_reason_message=shim_status.result.reason_message,
            )

        if shim_status.state in ("pulling", "creating"):
            return _SyncShimPullingStateResult(state=_ShimPullingState.WAITING)

    return _SyncShimPullingStateResult(
        state=_ShimPullingState.READY,
        job_runtime_data=jrd,
    )


@dataclass
class _SubmitJobToRunnerResult:
    success: bool
    set_running_status: bool = False
    job_runtime_data: Optional[JobRuntimeData] = None


@runner_ssh_tunnel(ports=[DSTACK_RUNNER_HTTP_PORT], retries=1)
def _submit_job_to_runner(
    ports: Dict[int, int],
    run: Run,
    job_model: JobModel,
    job: Job,
    jrd: Optional[JobRuntimeData],
    cluster_info: ClusterInfo,
    code: bytes,
    file_archives: Iterable[tuple[uuid.UUID, bytes]],
    secrets: Dict[str, str],
    repo_credentials: Optional[RemoteRepoCreds],
    success_if_not_available: bool,
) -> Union[_SubmitJobToRunnerResult, Literal[False]]:
    logger.debug("%s: submitting job spec", fmt(job_model))
    logger.debug(
        "%s: repo clone URL is %s",
        fmt(job_model),
        None if repo_credentials is None else repo_credentials.clone_url,
    )
    instance = job_model.instance
    if instance is not None and (rci := get_instance_remote_connection_info(instance)) is not None:
        instance_env = rci.env
    else:
        instance_env = None

    runner_client = client.RunnerClient(port=ports[DSTACK_RUNNER_HTTP_PORT])
    if runner_client.healthcheck() is None:
        return _SubmitJobToRunnerResult(success=success_if_not_available)

    runner_client.submit_job(
        run=run,
        job=job,
        cluster_info=cluster_info,
        # Do not send all the secrets since interpolation is already done by the server.
        # TODO: Passing secrets may be necessary for filtering out secret values from logs.
        secrets={},
        repo_credentials=repo_credentials,
        instance_env=instance_env,
    )
    logger.debug("%s: uploading file archive(s)", fmt(job_model))
    for archive_id, archive in file_archives:
        runner_client.upload_archive(archive_id, archive)
    logger.debug("%s: uploading code", fmt(job_model))
    runner_client.upload_code(code)
    logger.debug("%s: starting job", fmt(job_model))
    job_info = runner_client.run_job()
    if job_info is not None:
        if jrd is not None:
            jrd = jrd.copy(
                update={"working_dir": job_info.working_dir, "username": job_info.username}
            )
    return _SubmitJobToRunnerResult(
        success=True,
        set_running_status=True,
        job_runtime_data=jrd,
    )


@dataclass
class _ProcessRunningResult:
    job_update_map: _JobUpdateMap = field(default_factory=_JobUpdateMap)


@runner_ssh_tunnel(ports=[DSTACK_RUNNER_HTTP_PORT])
def _process_running(
    ports: Dict[int, int],
    run_model: RunModel,
    job_model: JobModel,
) -> Union[_ProcessRunningResult, Literal[False]]:
    runner_client = client.RunnerClient(port=ports[DSTACK_RUNNER_HTTP_PORT])
    timestamp = job_model.runner_timestamp or 0
    resp = runner_client.pull(timestamp)
    logs_services.write_logs(
        project=run_model.project,
        run_name=run_model.run_name,
        job_submission_id=job_model.id,
        runner_logs=resp.runner_logs,
        job_logs=resp.job_logs,
    )
    result = _ProcessRunningResult(
        job_update_map=_JobUpdateMap(runner_timestamp=resp.last_updated)
    )
    if len(resp.job_states) > 0:
        latest_state_event = resp.job_states[-1]
        latest_status = latest_state_event.state
        if latest_status == JobStatus.DONE:
            _terminate_job(
                job_model=job_model,
                job_update_map=result.job_update_map,
                termination_reason=JobTerminationReason.DONE_BY_RUNNER,
                termination_reason_message=None,
            )
        elif latest_status in {JobStatus.FAILED, JobStatus.TERMINATED}:
            termination_reason = JobTerminationReason.CONTAINER_EXITED_WITH_ERROR
            if latest_state_event.termination_reason:
                termination_reason = JobTerminationReason(
                    latest_state_event.termination_reason.lower()
                )
            _terminate_job(
                job_model=job_model,
                job_update_map=result.job_update_map,
                termination_reason=termination_reason,
                termination_reason_message=latest_state_event.termination_message,
            )
        if latest_state_event.exit_status is not None:
            result.job_update_map["exit_status"] = latest_state_event.exit_status
            if latest_state_event.exit_status != 0:
                logger.info(
                    "%s: non-zero exit status %s", fmt(job_model), latest_state_event.exit_status
                )
    else:
        _terminate_if_inactivity_duration_exceeded(
            run_model=run_model,
            job_model=job_model,
            job_update_map=result.job_update_map,
            no_connections_secs=resp.no_connections_secs,
        )
    return result


def _terminate_if_inactivity_duration_exceeded(
    run_model: RunModel,
    job_model: JobModel,
    job_update_map: _JobUpdateMap,
    no_connections_secs: Optional[int],
) -> None:
    conf = RunSpec.__response__.parse_raw(run_model.run_spec).configuration
    if not isinstance(conf, DevEnvironmentConfiguration) or not isinstance(
        conf.inactivity_duration, int
    ):
        job_update_map["inactivity_secs"] = None
        return

    logger.debug("%s: no SSH connections for %s seconds", fmt(job_model), no_connections_secs)
    job_update_map["inactivity_secs"] = no_connections_secs
    if no_connections_secs is None:
        # TODO(0.19 or earlier): make no_connections_secs required
        _terminate_job(
            job_model=job_model,
            job_update_map=job_update_map,
            termination_reason=JobTerminationReason.INTERRUPTED_BY_NO_CAPACITY,
            termination_reason_message=(
                "The selected instance was created before dstack 0.18.41"
                " and does not support inactivity_duration"
            ),
        )
    elif no_connections_secs >= conf.inactivity_duration:
        _terminate_job(
            job_model=job_model,
            job_update_map=job_update_map,
            termination_reason=JobTerminationReason.INACTIVITY_DURATION_EXCEEDED,
            termination_reason_message=(
                f"The job was inactive for {no_connections_secs} seconds,"
                f" exceeding the inactivity_duration of {conf.inactivity_duration} seconds"
            ),
        )


def _should_terminate_job_due_to_disconnect(disconnected_at: Optional[datetime]) -> bool:
    if disconnected_at is None:
        return False
    return get_current_datetime() > disconnected_at + JOB_DISCONNECTED_RETRY_TIMEOUT


def _set_disconnected_at_now(job_model: JobModel, result: _ProcessResult) -> None:
    if _get_result_disconnected_at(job_model, result) is None:
        result.job_update_map["disconnected_at"] = get_current_datetime()


def _reset_disconnected_at(job_model: JobModel, result: _ProcessResult) -> None:
    if _get_result_disconnected_at(job_model, result) is not None:
        result.job_update_map["disconnected_at"] = None


def _get_cluster_info(
    jobs: list[Job],
    replica_num: int,
    job_provisioning_data: JobProvisioningData,
    job_runtime_data: Optional[JobRuntimeData],
) -> ClusterInfo:
    job_ips = []
    for job in jobs:
        if job.job_spec.replica_num == replica_num:
            job_ips.append(
                get_or_error(job.job_submissions[-1].job_provisioning_data).internal_ip or ""
            )
    gpus_per_job = len(job_provisioning_data.instance_type.resources.gpus)
    if job_runtime_data is not None and job_runtime_data.offer is not None:
        gpus_per_job = len(job_runtime_data.offer.instance.resources.gpus)
    return ClusterInfo(
        job_ips=job_ips,
        master_job_ip=job_ips[0],
        gpus_per_job=gpus_per_job,
    )


def _get_repo_code_hash(run: Run, job: Job) -> Optional[str]:
    # TODO: drop this function when supporting jobs submitted before 0.19.17 is no longer relevant.
    if (
        job.job_spec.repo_code_hash is None
        and run.run_spec.repo_code_hash is not None
        and job.job_submissions[-1].deployment_num == run.deployment_num
    ):
        return run.run_spec.repo_code_hash
    return job.job_spec.repo_code_hash


async def _get_job_code(project: ProjectModel, repo: RepoModel, code_hash: Optional[str]) -> bytes:
    if code_hash is None:
        return b""
    async with get_session_ctx() as session:
        code_model = await get_code_model(session=session, repo=repo, code_hash=code_hash)
    if code_model is None:
        return b""
    if code_model.blob is not None:
        return code_model.blob
    storage = get_default_storage()
    if storage is None:
        return b""
    blob = await run_async(
        storage.get_code,
        project.name,
        repo.name,
        code_hash,
    )
    if blob is None:
        logger.error(
            "Failed to get repo code hash %s from storage for repo %s", code_hash, repo.name
        )
        return b""
    return blob


async def _get_job_file_archives(
    archive_mappings: Iterable[FileArchiveMapping],
    user: UserModel,
) -> list[tuple[uuid.UUID, bytes]]:
    archives: list[tuple[uuid.UUID, bytes]] = []
    for archive_mapping in archive_mappings:
        archive_blob = await _get_job_file_archive(archive_id=archive_mapping.id, user=user)
        archives.append((archive_mapping.id, archive_blob))
    return archives


async def _get_job_file_archive(archive_id: uuid.UUID, user: UserModel) -> bytes:
    async with get_session_ctx() as session:
        archive_model = await files_services.get_archive_model(session, id=archive_id, user=user)
    if archive_model is None:
        return b""
    if archive_model.blob is not None:
        return archive_model.blob
    storage = get_default_storage()
    if storage is None:
        return b""
    blob = await run_async(
        storage.get_archive,
        str(archive_model.user_id),
        archive_model.blob_hash,
    )
    if blob is None:
        logger.error("Failed to get file archive %s from storage", archive_id)
        return b""
    return blob


def _interpolate_secrets(secrets: Dict[str, str], job_spec: JobSpec) -> None:
    interpolate = VariablesInterpolator({"secrets": secrets}).interpolate_or_error
    job_spec.env = {k: interpolate(v) for k, v in job_spec.env.items()}
    if job_spec.registry_auth is not None:
        job_spec.registry_auth = RegistryAuth(
            username=interpolate(job_spec.registry_auth.username),
            password=interpolate(job_spec.registry_auth.password),
        )


def _emit_reachability_change_event(
    session: AsyncSession,
    job_model: JobModel,
    old_disconnected_at: Optional[datetime],
    new_disconnected_at: Optional[datetime],
) -> None:
    if old_disconnected_at is None and new_disconnected_at is not None:
        events.emit(
            session,
            "Job became unreachable",
            actor=events.SystemActor(),
            targets=[events.Target.from_model(job_model)],
        )
    elif old_disconnected_at is not None and new_disconnected_at is None:
        events.emit(
            session,
            "Job became reachable",
            actor=events.SystemActor(),
            targets=[events.Target.from_model(job_model)],
        )


def _terminate_job(
    job_model: JobModel,
    job_update_map: _JobUpdateMap,
    termination_reason: JobTerminationReason,
    termination_reason_message: Optional[str],
) -> None:
    job_update_map["termination_reason"] = termination_reason
    job_update_map["termination_reason_message"] = termination_reason_message
    _set_job_update_status(job_model, job_update_map, JobStatus.TERMINATING)


def _set_job_update_status(
    job_model: JobModel,
    job_update_map: _JobUpdateMap,
    new_status: JobStatus,
) -> None:
    if job_update_map.get("status", job_model.status) != new_status:
        job_update_map["status"] = new_status


def _set_job_status(job_model: JobModel, result: _ProcessResult, new_status: JobStatus) -> None:
    _set_job_update_status(job_model, result.job_update_map, new_status)


def _set_job_runtime_data(result: _ProcessResult, jrd: Optional[JobRuntimeData]) -> None:
    result.job_update_map["job_runtime_data"] = None if jrd is None else jrd.json()


def _apply_submit_job_to_runner_result(
    job_model: JobModel,
    result: _ProcessResult,
    submit_result: _SubmitJobToRunnerResult,
) -> None:
    if submit_result.job_runtime_data is not None:
        _set_job_runtime_data(result, submit_result.job_runtime_data)
    if submit_result.set_running_status:
        _set_job_status(job_model, result, JobStatus.RUNNING)


# Convention: _get_result_* helpers merge the loaded job_model state with any pending
# updates recorded in result.job_update_map. Always use these (not job_model.attr directly)
# when the field may have been updated earlier in the same processing cycle.


def _get_result_status(job_model: JobModel, result: _ProcessResult) -> JobStatus:
    return result.job_update_map.get("status", job_model.status)


def _get_result_disconnected_at(job_model: JobModel, result: _ProcessResult) -> Optional[datetime]:
    return result.job_update_map.get("disconnected_at", job_model.disconnected_at)


def _get_result_job_runtime_data(
    job_model: JobModel, result: _ProcessResult
) -> Optional[JobRuntimeData]:
    jrd = result.job_update_map.get("job_runtime_data", job_model.job_runtime_data)
    if jrd is None:
        return None
    return JobRuntimeData.__response__.parse_raw(jrd)


def _get_result_registered(job_model: JobModel, result: _ProcessResult) -> bool:
    return result.job_update_map.get("registered", job_model.registered)
