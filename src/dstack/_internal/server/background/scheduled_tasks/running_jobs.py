import asyncio
import enum
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, List, Literal, Optional, Union

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, contains_eager, joinedload, load_only

from dstack._internal.core.consts import DSTACK_RUNNER_HTTP_PORT, DSTACK_SHIM_HTTP_PORT
from dstack._internal.core.errors import GatewayError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import NetworkMode, RegistryAuth
from dstack._internal.core.models.configurations import DevEnvironmentConfiguration
from dstack._internal.core.models.files import FileArchiveMapping
from dstack._internal.core.models.instances import (
    InstanceStatus,
    SSHConnectionParams,
)
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
    ProbeSpec,
    Run,
    RunStatus,
)
from dstack._internal.core.models.volumes import InstanceMountPoint, Volume, VolumeMountPoint
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
from dstack._internal.server.services import events, services
from dstack._internal.server.services import files as files_services
from dstack._internal.server.services import logs as logs_services
from dstack._internal.server.services.backends.provisioning import (
    get_instance_specific_gpu_devices,
    get_instance_specific_mounts,
    resolve_provisioning_image_name,
)
from dstack._internal.server.services.instances import (
    get_instance_remote_connection_info,
    get_instance_ssh_private_keys,
)
from dstack._internal.server.services.jobs import (
    find_job,
    get_job_attached_volumes,
    get_job_runtime_data,
    get_job_spec,
    is_master_job,
    job_model_to_job_submission,
    switch_job_status,
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
from dstack._internal.server.services.runs import (
    get_run_spec,
    is_job_ready,
    run_model_to_run,
)
from dstack._internal.server.services.secrets import get_project_secrets_mapping
from dstack._internal.server.services.storage import get_default_storage
from dstack._internal.server.utils import sentry_utils
from dstack._internal.utils import common as common_utils
from dstack._internal.utils.interpolator import InterpolatorError, VariablesInterpolator
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


MIN_PROCESSING_INTERVAL = timedelta(seconds=10)
# Minimum time before terminating active job in case of connectivity issues.
# Should be sufficient to survive most problems caused by
# the server network flickering and providers' glitches.
JOB_DISCONNECTED_RETRY_TIMEOUT = timedelta(minutes=2)


async def process_running_jobs(batch_size: int = 1):
    tasks = []
    for _ in range(batch_size):
        tasks.append(_process_next_running_job())
    await asyncio.gather(*tasks)


@sentry_utils.instrument_scheduled_task
async def _process_next_running_job():
    lock, lockset = get_locker(get_db().dialect_name).get_lockset(JobModel.__tablename__)
    async with get_session_ctx() as session:
        async with lock:
            res = await session.execute(
                select(JobModel)
                .join(JobModel.run)
                .where(
                    JobModel.status.in_(
                        [JobStatus.PROVISIONING, JobStatus.PULLING, JobStatus.RUNNING]
                    ),
                    RunModel.status.not_in([RunStatus.TERMINATING]),
                    JobModel.id.not_in(lockset),
                    JobModel.last_processed_at
                    < common_utils.get_current_datetime() - MIN_PROCESSING_INTERVAL,
                )
                .options(load_only(JobModel.id))
                .order_by(JobModel.last_processed_at.asc())
                .limit(1)
                .with_for_update(
                    skip_locked=True,
                    key_share=True,
                    of=JobModel,
                )
            )
            job_model = res.unique().scalar()
            if job_model is None:
                return
            lockset.add(job_model.id)
        job_model_id = job_model.id
        try:
            await _process_running_job(session=session, job_model=job_model)
        finally:
            lockset.difference_update([job_model_id])


@dataclass
class _RunningJobContext:
    job_model: JobModel
    run_model: RunModel
    repo_model: RepoModel
    project: ProjectModel
    run: Run
    job: Job
    job_submission: JobSubmission
    job_provisioning_data: Optional[JobProvisioningData]
    initial_status: JobStatus
    server_ssh_private_keys: Optional[tuple[str, Optional[str]]] = None


@dataclass
class _RunningJobStartupContext:
    cluster_info: ClusterInfo
    volumes: list[Volume]
    secrets: dict[str, str]
    repo_creds: Optional[RemoteRepoCreds]


async def _process_running_job(session: AsyncSession, job_model: JobModel):
    context = await _load_running_job_context(session=session, job_model=job_model)
    if context.job_provisioning_data is None:
        logger.error("%s: job_provisioning_data of an active job is None", fmt(context.job_model))
        await _terminate_running_job(
            session=session,
            job_model=context.job_model,
            termination_reason=JobTerminationReason.TERMINATED_BY_SERVER,
            termination_reason_message="Unexpected server error: job_provisioning_data of an active job is None",
        )
        return

    startup_context = None
    if context.initial_status in [JobStatus.PROVISIONING, JobStatus.PULLING]:
        startup_context = await _prepare_running_job_startup_context(
            session=session,
            context=context,
        )
        if startup_context is None:
            return

    if context.initial_status == JobStatus.PROVISIONING:
        await _process_running_job_provisioning_state(
            session=session,
            context=context,
            startup_context=common_utils.get_or_error(startup_context),
        )
    elif context.initial_status == JobStatus.PULLING:
        await _process_running_job_pulling_state(
            session=session,
            context=context,
            startup_context=common_utils.get_or_error(startup_context),
        )
    else:
        await _process_running_job_running_state(
            session=session,
            context=context,
        )

    if context.job_model.status == JobStatus.RUNNING:
        if context.initial_status != JobStatus.RUNNING:
            _initialize_running_job_probes(job_model=context.job_model, job=context.job)
        await _maybe_register_replica(
            session,
            run_model=context.run_model,
            run=context.run,
            job_model=context.job_model,
            probe_specs=context.job.job_spec.probes,
        )
        await _check_gpu_utilization(session, job_model=context.job_model, job=context.job)

    await _mark_job_processed(session=session, job_model=context.job_model)


async def _load_running_job_context(
    session: AsyncSession, job_model: JobModel
) -> _RunningJobContext:
    job_model = await _refetch_job_model(session, job_model)
    run_model = await _fetch_run_model(session, job_model.run_id)
    run = run_model_to_run(run_model, include_sensitive=True)
    job_submission = job_model_to_job_submission(job_model)
    server_ssh_private_keys = get_instance_ssh_private_keys(
        common_utils.get_or_error(job_model.instance)
    )
    return _RunningJobContext(
        job_model=job_model,
        run_model=run_model,
        repo_model=run_model.repo,
        project=run_model.project,
        run=run,
        job=find_job(run.jobs, job_model.replica_num, job_model.job_num),
        job_submission=job_submission,
        job_provisioning_data=job_submission.job_provisioning_data,
        initial_status=job_model.status,
        server_ssh_private_keys=server_ssh_private_keys,
    )


async def _prepare_running_job_startup_context(
    session: AsyncSession,
    context: _RunningJobContext,
) -> Optional[_RunningJobStartupContext]:
    job_provisioning_data = common_utils.get_or_error(context.job_provisioning_data)

    for other_job in context.run.jobs:
        if (
            other_job.job_spec.replica_num == context.job.job_spec.replica_num
            and other_job.job_submissions[-1].status == JobStatus.SUBMITTED
        ):
            logger.debug(
                "%s: waiting for all jobs in the replica to be provisioned",
                fmt(context.job_model),
            )
            await _mark_job_processed(session=session, job_model=context.job_model)
            return None

    cluster_info = _get_cluster_info(
        jobs=context.run.jobs,
        replica_num=context.job.job_spec.replica_num,
        job_provisioning_data=job_provisioning_data,
        job_runtime_data=context.job_submission.job_runtime_data,
    )

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
    repo_creds = repo_model_to_repo_head_with_creds(
        context.repo_model,
        repo_creds_model,
    ).repo_creds

    secrets = await get_project_secrets_mapping(session=session, project=context.project)
    try:
        _interpolate_secrets(secrets, context.job.job_spec)
    except InterpolatorError as e:
        await _terminate_running_job(
            session=session,
            job_model=context.job_model,
            termination_reason=JobTerminationReason.TERMINATED_BY_SERVER,
            termination_reason_message=f"Secrets interpolation error: {e.args[0]}",
        )
        return None

    return _RunningJobStartupContext(
        cluster_info=cluster_info,
        volumes=volumes,
        secrets=secrets,
        repo_creds=repo_creds,
    )


async def _refetch_job_model(session: AsyncSession, job_model: JobModel) -> JobModel:
    res = await session.execute(
        select(JobModel)
        .where(JobModel.id == job_model.id)
        .options(joinedload(JobModel.instance).joinedload(InstanceModel.project))
        .options(joinedload(JobModel.probes).load_only(ProbeModel.success_streak))
        .execution_options(populate_existing=True)
    )
    return res.unique().scalar_one()


async def _fetch_run_model(session: AsyncSession, run_id: uuid.UUID) -> RunModel:
    # Select only latest submissions for every job.
    latest_submissions_sq = (
        select(
            JobModel.run_id.label("run_id"),
            JobModel.replica_num.label("replica_num"),
            JobModel.job_num.label("job_num"),
            func.max(JobModel.submission_num).label("max_submission_num"),
        )
        .where(JobModel.run_id == run_id)
        .group_by(JobModel.run_id, JobModel.replica_num, JobModel.job_num)
        .subquery()
    )
    job_alias = aliased(JobModel)
    res = await session.execute(
        select(RunModel)
        .where(RunModel.id == run_id)
        .join(job_alias, job_alias.run_id == RunModel.id)
        .join(
            latest_submissions_sq,
            onclause=and_(
                job_alias.run_id == latest_submissions_sq.c.run_id,
                job_alias.replica_num == latest_submissions_sq.c.replica_num,
                job_alias.job_num == latest_submissions_sq.c.job_num,
                job_alias.submission_num == latest_submissions_sq.c.max_submission_num,
            ),
        )
        .options(joinedload(RunModel.project))
        .options(joinedload(RunModel.user))
        .options(joinedload(RunModel.repo))
        .options(joinedload(RunModel.fleet).load_only(FleetModel.id, FleetModel.name))
        .options(contains_eager(RunModel.jobs, alias=job_alias))
    )
    return res.unique().scalar_one()


async def _process_running_job_provisioning_state(
    session: AsyncSession,
    context: _RunningJobContext,
    startup_context: _RunningJobStartupContext,
) -> None:
    job_provisioning_data = common_utils.get_or_error(context.job_provisioning_data)
    server_ssh_private_keys = common_utils.get_or_error(context.server_ssh_private_keys)

    if job_provisioning_data.hostname is None:
        await _wait_for_instance_provisioning_data(session, context.job_model)
        return
    if _should_wait_for_other_nodes(context.run, context.job, context.job_model):
        return

    # fails are acceptable until timeout is exceeded
    success = False
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
            # No need to update ~/.ssh/authorized_keys when running shim locally
            user_ssh_key = ""
        success = await common_utils.run_async(
            _process_provisioning_with_shim,
            server_ssh_private_keys,
            job_provisioning_data,
            None,
            session=session,
            run=context.run,
            job_model=context.job_model,
            jpd=job_provisioning_data,
            volumes=startup_context.volumes,
            registry_auth=context.job.job_spec.registry_auth,
            public_keys=public_keys,
            ssh_user=ssh_user,
            ssh_key=user_ssh_key,
        )
    else:
        logger.debug(
            "%s: process provisioning job without shim, age=%s",
            fmt(context.job_model),
            context.job_submission.age,
        )
        runner_availability = await common_utils.run_async(
            _get_runner_availability,
            server_ssh_private_keys,
            job_provisioning_data,
            None,
        )
        if runner_availability == _RunnerAvailability.AVAILABLE:
            file_archives = await _get_job_file_archives(
                session=session,
                archive_mappings=context.job.job_spec.file_archives,
                user=context.run_model.user,
            )
            code = await _get_job_code(
                session=session,
                project=context.project,
                repo=context.repo_model,
                code_hash=_get_repo_code_hash(context.run, context.job),
            )
            success = await common_utils.run_async(
                _submit_job_to_runner,
                server_ssh_private_keys,
                job_provisioning_data,
                None,
                session=session,
                run=context.run,
                job_model=context.job_model,
                job=context.job,
                cluster_info=startup_context.cluster_info,
                code=code,
                file_archives=file_archives,
                secrets=startup_context.secrets,
                repo_credentials=startup_context.repo_creds,
                success_if_not_available=False,
            )

    if success:
        return

    # check timeout
    provisioning_timeout = get_provisioning_timeout(
        backend_type=job_provisioning_data.get_base_backend(),
        instance_type_name=job_provisioning_data.instance_type.name,
    )
    if context.job_submission.age > provisioning_timeout:
        context.job_model.termination_reason = JobTerminationReason.WAITING_RUNNER_LIMIT_EXCEEDED
        context.job_model.termination_reason_message = (
            f"Runner did not become available within {provisioning_timeout.total_seconds()}s."
            f" Job submission age: {context.job_submission.age.total_seconds()}s)"
        )
        switch_job_status(session, context.job_model, JobStatus.TERMINATING)
        # instance will be emptied by process_terminating_jobs


async def _process_running_job_pulling_state(
    session: AsyncSession,
    context: _RunningJobContext,
    startup_context: _RunningJobStartupContext,
) -> None:
    job_provisioning_data = common_utils.get_or_error(context.job_provisioning_data)
    server_ssh_private_keys = common_utils.get_or_error(context.server_ssh_private_keys)

    logger.debug(
        "%s: process pulling job with shim, age=%s",
        fmt(context.job_model),
        context.job_submission.age,
    )
    shim_state = await common_utils.run_async(
        _sync_shim_pulling_state,
        server_ssh_private_keys,
        job_provisioning_data,
        None,
        job_model=context.job_model,
    )
    if shim_state == _ShimPullingState.WAITING:
        _reset_disconnected_at(session, context.job_model)
        return

    if shim_state == _ShimPullingState.READY:
        job_runtime_data = get_job_runtime_data(context.job_model)
        runner_availability = await common_utils.run_async(
            _get_runner_availability,
            server_ssh_private_keys,
            job_provisioning_data,
            job_runtime_data,
        )
        if runner_availability == _RunnerAvailability.UNAVAILABLE:
            _reset_disconnected_at(session, context.job_model)
            return

        if runner_availability == _RunnerAvailability.AVAILABLE:
            file_archives = await _get_job_file_archives(
                session=session,
                archive_mappings=context.job.job_spec.file_archives,
                user=context.run_model.user,
            )
            code = await _get_job_code(
                session=session,
                project=context.project,
                repo=context.repo_model,
                code_hash=_get_repo_code_hash(context.run, context.job),
            )
            success = await common_utils.run_async(
                _submit_job_to_runner,
                server_ssh_private_keys,
                job_provisioning_data,
                job_runtime_data,
                session=session,
                run=context.run,
                job_model=context.job_model,
                job=context.job,
                cluster_info=startup_context.cluster_info,
                code=code,
                file_archives=file_archives,
                secrets=startup_context.secrets,
                repo_credentials=startup_context.repo_creds,
                success_if_not_available=True,
            )
            if success:
                _reset_disconnected_at(session, context.job_model)
                return

    if context.job_model.termination_reason:
        logger.warning(
            "%s: failed due to %s, age=%s",
            fmt(context.job_model),
            context.job_model.termination_reason.value,
            context.job_submission.age,
        )
        switch_job_status(session, context.job_model, JobStatus.TERMINATING)
        # job will be terminated and instance will be emptied by process_terminating_jobs
        return

    # No job_model.termination_reason set means ssh connection failed
    _set_disconnected_at_now(session, context.job_model)
    if not _should_terminate_job_due_to_disconnect(context.job_model):
        logger.warning(
            "%s: is unreachable, waiting for the instance to become reachable again, age=%s",
            fmt(context.job_model),
            context.job_submission.age,
        )
        return

    if job_provisioning_data.instance_type.resources.spot:
        context.job_model.termination_reason = JobTerminationReason.INTERRUPTED_BY_NO_CAPACITY
    else:
        context.job_model.termination_reason = JobTerminationReason.INSTANCE_UNREACHABLE
    context.job_model.termination_reason_message = "Instance is unreachable"
    switch_job_status(session, context.job_model, JobStatus.TERMINATING)


async def _process_running_job_running_state(
    session: AsyncSession,
    context: _RunningJobContext,
) -> None:
    job_provisioning_data = common_utils.get_or_error(context.job_provisioning_data)
    server_ssh_private_keys = common_utils.get_or_error(context.server_ssh_private_keys)

    logger.debug(
        "%s: process running job, age=%s",
        fmt(context.job_model),
        context.job_submission.age,
    )
    success = await common_utils.run_async(
        _process_running,
        server_ssh_private_keys,
        job_provisioning_data,
        context.job_submission.job_runtime_data,
        session=session,
        run_model=context.run_model,
        job_model=context.job_model,
    )

    if success:
        _reset_disconnected_at(session, context.job_model)
        return

    if context.job_model.termination_reason:
        logger.warning(
            "%s: failed due to %s, age=%s",
            fmt(context.job_model),
            context.job_model.termination_reason.value,
            context.job_submission.age,
        )
        switch_job_status(session, context.job_model, JobStatus.TERMINATING)
        # job will be terminated and instance will be emptied by process_terminating_jobs
        return

    # No job_model.termination_reason set means ssh connection failed
    _set_disconnected_at_now(session, context.job_model)
    if not _should_terminate_job_due_to_disconnect(context.job_model):
        logger.warning(
            "%s: is unreachable, waiting for the instance to become reachable again, age=%s",
            fmt(context.job_model),
            context.job_submission.age,
        )
        return

    if job_provisioning_data.instance_type.resources.spot:
        context.job_model.termination_reason = JobTerminationReason.INTERRUPTED_BY_NO_CAPACITY
    else:
        context.job_model.termination_reason = JobTerminationReason.INSTANCE_UNREACHABLE
    context.job_model.termination_reason_message = "Instance is unreachable"
    switch_job_status(session, context.job_model, JobStatus.TERMINATING)


async def _mark_job_processed(session: AsyncSession, job_model: JobModel) -> None:
    job_model.last_processed_at = common_utils.get_current_datetime()
    await session.commit()


async def _terminate_running_job(
    session: AsyncSession,
    job_model: JobModel,
    termination_reason: JobTerminationReason,
    termination_reason_message: str,
) -> None:
    job_model.termination_reason = termination_reason
    job_model.termination_reason_message = termination_reason_message
    switch_job_status(session, job_model, JobStatus.TERMINATING)
    await _mark_job_processed(session=session, job_model=job_model)


def _initialize_running_job_probes(job_model: JobModel, job: Job) -> None:
    job_model.probes = []
    for probe_num in range(len(job.job_spec.probes)):
        job_model.probes.append(
            ProbeModel(
                name=f"{job_model.job_name}-{probe_num}",
                probe_num=probe_num,
                due=common_utils.get_current_datetime(),
                success_streak=0,
                active=True,
            )
        )


async def _wait_for_instance_provisioning_data(session: AsyncSession, job_model: JobModel):
    """
    This function will be called until instance IP address appears
    in `job_model.instance.job_provisioning_data` or instance is terminated on timeout.
    """
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
        job_model.termination_reason = JobTerminationReason.WAITING_INSTANCE_LIMIT_EXCEEDED
        job_model.termination_reason_message = "Instance is terminated"
        switch_job_status(session, job_model, JobStatus.TERMINATING)
        return

    job_model.job_provisioning_data = job_model.instance.job_provisioning_data


def _should_wait_for_other_nodes(run: Run, job: Job, job_model: JobModel) -> bool:
    for other_job in run.jobs:
        if (
            other_job.job_spec.replica_num == job.job_spec.replica_num
            and other_job.job_submissions[-1].status == JobStatus.PROVISIONING
            and other_job.job_submissions[-1].job_provisioning_data is not None
            and other_job.job_submissions[-1].job_provisioning_data.hostname is None
        ):
            logger.debug(
                "%s: waiting for other job to have IP assigned",
                fmt(job_model),
            )
            return True
    master_job = find_job(run.jobs, job.job_spec.replica_num, 0)
    if (
        job.job_spec.job_num != 0
        and run.run_spec.merged_profile.startup_order == StartupOrder.MASTER_FIRST
        and master_job.job_submissions[-1].status != JobStatus.RUNNING
    ):
        logger.debug(
            "%s: waiting for master job to become running",
            fmt(job_model),
        )
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
                logger.debug(
                    "%s: waiting for worker job to become running",
                    fmt(job_model),
                )
                return True
    return False


@runner_ssh_tunnel(ports=[DSTACK_SHIM_HTTP_PORT], retries=1)
def _process_provisioning_with_shim(
    ports: Dict[int, int],
    session: AsyncSession,
    run: Run,
    job_model: JobModel,
    jpd: JobProvisioningData,
    volumes: List[Volume],
    registry_auth: Optional[RegistryAuth],
    public_keys: List[str],
    ssh_user: str,
    ssh_key: str,
) -> bool:
    """
    Possible next states:
    - JobStatus.PULLING if shim is available
    - JobStatus.TERMINATING if timeout is exceeded

    Returns:
        is successful
    """
    job_spec = get_job_spec(job_model)

    shim_client = client.ShimClient(port=ports[DSTACK_SHIM_HTTP_PORT])

    resp = shim_client.healthcheck()
    if resp is None:
        logger.debug("%s: shim is not available yet", fmt(job_model))
        return False  # shim is not available yet

    registry_username = ""
    registry_password = ""
    if registry_auth is not None:
        registry_username = registry_auth.username
        registry_password = registry_auth.password

    volume_mounts: List[VolumeMountPoint] = []
    instance_mounts: List[InstanceMountPoint] = []
    for mount in run.run_spec.configuration.volumes:
        if isinstance(mount, VolumeMountPoint):
            volume_mounts.append(mount.copy())
        elif isinstance(mount, InstanceMountPoint):
            instance_mounts.append(mount)
        else:
            assert False, f"unexpected mount point: {mount!r}"

    # Run configuration may specify list of possible volume names.
    # We should resolve in to the actual volume attached.
    for volume, volume_mount in zip(volumes, volume_mounts):
        volume_mount.name = volume.name

    instance_mounts += get_instance_specific_mounts(jpd.backend, jpd.instance_type.name)

    gpu_devices = get_instance_specific_gpu_devices(jpd.backend, jpd.instance_type.name)

    container_user = "root"

    job_runtime_data = get_job_runtime_data(job_model)
    # should check for None, as there may be older jobs submitted before
    # JobRuntimeData was introduced
    if job_runtime_data is not None:
        gpu = job_runtime_data.gpu
        cpu = job_runtime_data.cpu
        memory = job_runtime_data.memory
        network_mode = job_runtime_data.network_mode
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
            # This can happen when we lost connection to the runner (e.g., network issues), marked
            # the job as failed, released the instance (status=BUSY->IDLE, job_id={id}->None),
            # but the job container is in fact alive, running the previous job. As we force-stop
            # the container via shim API when cancelling the current job anyway (when either the
            # user aborts the submission process or the submission deadline is reached), it's safe
            # to kill the previous job container now, making the shim available
            # (state=running->pending) for the next try.
            logger.warning(
                "%s: failed to submit, shim is already running a job, stopping it now, retry later",
                fmt(job_model),
            )
            shim_client.stop(force=True)
            return False

    switch_job_status(session, job_model, JobStatus.PULLING)
    return True


class _RunnerAvailability(enum.Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class _ShimPullingState(enum.Enum):
    WAITING = "waiting"
    READY = "ready"


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
) -> Union[Literal[False], _ShimPullingState]:
    shim_client = client.ShimClient(port=ports[DSTACK_SHIM_HTTP_PORT])
    if shim_client.is_api_v2_supported():  # raises error if shim is down, causes retry
        task = shim_client.get_task(job_model.id)

        # If task goes to terminated before the job is submitted to runner, then an error occurred
        if task.status == TaskStatus.TERMINATED:
            logger.warning(
                "shim failed to execute job %s: %s (%s)",
                job_model.job_name,
                task.termination_reason,
                task.termination_message,
            )
            logger.debug("task status: %s", task.dict())
            job_model.termination_reason = JobTerminationReason(task.termination_reason.lower())
            job_model.termination_reason_message = task.termination_message
            return False

        if task.status != TaskStatus.RUNNING:
            return _ShimPullingState.WAITING

        job_runtime_data = get_job_runtime_data(job_model)
        # should check for None, as there may be older jobs submitted before
        # JobRuntimeData was introduced
        if job_runtime_data is not None:
            # port mapping is not yet available, waiting
            if task.ports is None:
                return _ShimPullingState.WAITING
            job_runtime_data.ports = {pm.container: pm.host for pm in task.ports}
            job_model.job_runtime_data = job_runtime_data.json()
    else:
        shim_status = shim_client.pull()  # raises error if shim is down, causes retry

        # If shim goes to pending before the job is submitted to runner, then an error occurred
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
            job_model.termination_reason = JobTerminationReason(shim_status.result.reason.lower())
            job_model.termination_reason_message = shim_status.result.reason_message
            return False

        if shim_status.state in ("pulling", "creating"):
            return _ShimPullingState.WAITING

    return _ShimPullingState.READY


@runner_ssh_tunnel(ports=[DSTACK_RUNNER_HTTP_PORT])
def _process_running(
    ports: Dict[int, int],
    session: AsyncSession,
    run_model: RunModel,
    job_model: JobModel,
) -> bool:
    """
    Possible next states:
    - JobStatus.TERMINATING if runner is not available
    - Any status received from runner

    Returns:
        is successful
    """
    runner_client = client.RunnerClient(port=ports[DSTACK_RUNNER_HTTP_PORT])
    timestamp = 0
    if job_model.runner_timestamp is not None:
        timestamp = job_model.runner_timestamp
    resp = runner_client.pull(timestamp)  # raises error if runner is down, causes retry
    job_model.runner_timestamp = resp.last_updated
    # may raise LogStorageError, causing a retry
    logs_services.write_logs(
        project=run_model.project,
        run_name=run_model.run_name,
        job_submission_id=job_model.id,
        runner_logs=resp.runner_logs,
        job_logs=resp.job_logs,
    )
    if len(resp.job_states) > 0:
        latest_state_event = resp.job_states[-1]
        latest_status = latest_state_event.state
        if latest_status == JobStatus.DONE:
            job_model.termination_reason = JobTerminationReason.DONE_BY_RUNNER
            switch_job_status(session, job_model, JobStatus.TERMINATING)
        elif latest_status in {JobStatus.FAILED, JobStatus.TERMINATED}:
            job_model.termination_reason = JobTerminationReason.CONTAINER_EXITED_WITH_ERROR
            if latest_state_event.termination_reason:
                job_model.termination_reason = JobTerminationReason(
                    latest_state_event.termination_reason.lower()
                )
            if latest_state_event.termination_message:
                job_model.termination_reason_message = latest_state_event.termination_message
            switch_job_status(session, job_model, JobStatus.TERMINATING)
        if (exit_status := latest_state_event.exit_status) is not None:
            job_model.exit_status = exit_status
            if exit_status != 0:
                logger.info("%s: non-zero exit status %s", fmt(job_model), exit_status)
    else:
        _terminate_if_inactivity_duration_exceeded(
            session, run_model, job_model, resp.no_connections_secs
        )
    return True


def _terminate_if_inactivity_duration_exceeded(
    session: AsyncSession,
    run_model: RunModel,
    job_model: JobModel,
    no_connections_secs: Optional[int],
) -> None:
    conf = get_run_spec(run_model).configuration
    if not isinstance(conf, DevEnvironmentConfiguration) or not isinstance(
        conf.inactivity_duration, int
    ):
        # reset in case inactivity_duration was disabled via in-place update
        job_model.inactivity_secs = None
        return
    logger.debug("%s: no SSH connections for %s seconds", fmt(job_model), no_connections_secs)
    job_model.inactivity_secs = no_connections_secs
    if no_connections_secs is None:
        # TODO(0.19 or earlier): make no_connections_secs required
        job_model.termination_reason = JobTerminationReason.INTERRUPTED_BY_NO_CAPACITY
        job_model.termination_reason_message = (
            "The selected instance was created before dstack 0.18.41"
            " and does not support inactivity_duration"
        )
        switch_job_status(session, job_model, JobStatus.TERMINATING)
    elif no_connections_secs >= conf.inactivity_duration:
        # TODO(0.19 or earlier): set JobTerminationReason.INACTIVITY_DURATION_EXCEEDED
        job_model.termination_reason = JobTerminationReason.TERMINATED_BY_SERVER
        job_model.termination_reason_message = (
            f"The job was inactive for {no_connections_secs} seconds,"
            f" exceeding the inactivity_duration of {conf.inactivity_duration} seconds"
        )
        switch_job_status(session, job_model, JobStatus.TERMINATING)


def _should_terminate_job_due_to_disconnect(job_model: JobModel) -> bool:
    if job_model.disconnected_at is None:
        return False
    return (
        common_utils.get_current_datetime()
        > job_model.disconnected_at + JOB_DISCONNECTED_RETRY_TIMEOUT
    )


async def _maybe_register_replica(
    session: AsyncSession,
    run_model: RunModel,
    run: Run,
    job_model: JobModel,
    probe_specs: Iterable[ProbeSpec],
) -> None:
    """
    Register the replica represented by this job to receive service requests if it is ready.
    """

    if (
        run.run_spec.configuration.type != "service"
        or job_model.registered
        or job_model.job_num != 0  # only the first job in the replica receives service requests
        or not is_job_ready(job_model.probes, probe_specs)
    ):
        return

    ssh_head_proxy: Optional[SSHConnectionParams] = None
    ssh_head_proxy_private_key: Optional[str] = None
    instance = common_utils.get_or_error(job_model.instance)
    rci = get_instance_remote_connection_info(instance)
    if rci is not None and rci.ssh_proxy is not None:
        ssh_head_proxy = rci.ssh_proxy
        ssh_head_proxy_keys = common_utils.get_or_error(rci.ssh_proxy_keys)
        ssh_head_proxy_private_key = ssh_head_proxy_keys[0].private
    try:
        await services.register_replica(
            session,
            run_model.gateway_id,
            run,
            job_model,
            ssh_head_proxy,
            ssh_head_proxy_private_key,
        )
    except GatewayError as e:
        logger.warning(
            "%s: failed to register service replica: %s",
            fmt(job_model),
            e,
        )
        job_model.termination_reason = JobTerminationReason.GATEWAY_ERROR
        # Not including e.args[0] in the message to avoid exposing internal details
        job_model.termination_reason_message = "Failed to register service replica"
        switch_job_status(session, job_model, JobStatus.TERMINATING)


async def _check_gpu_utilization(session: AsyncSession, job_model: JobModel, job: Job) -> None:
    policy = job.job_spec.utilization_policy
    if policy is None:
        return
    after = common_utils.get_current_datetime() - timedelta(seconds=policy.time_window)
    job_metrics = await get_job_metrics(session, job_model, after=after)
    gpus_util_metrics: list[Metric] = []
    for metric in job_metrics.metrics:
        if metric.name.startswith("gpu_util_percent_gpu"):
            gpus_util_metrics.append(metric)
    if not gpus_util_metrics or gpus_util_metrics[0].timestamps[-1] > after + timedelta(minutes=1):
        # Job has started recently, not enough points collected.
        # Assuming that metrics collection interval less than 1 minute.
        logger.debug("%s: GPU utilization check: not enough samples", fmt(job_model))
        return
    if _should_terminate_due_to_low_gpu_util(
        policy.min_gpu_utilization, [m.values for m in gpus_util_metrics]
    ):
        logger.debug("%s: GPU utilization check: terminating", fmt(job_model))
        # TODO(0.19 or earlier): set JobTerminationReason.TERMINATED_DUE_TO_UTILIZATION_POLICY
        job_model.termination_reason = JobTerminationReason.TERMINATED_BY_SERVER
        job_model.termination_reason_message = (
            f"The job GPU utilization below {policy.min_gpu_utilization}%"
            f" for {policy.time_window} seconds"
        )
        switch_job_status(session, job_model, JobStatus.TERMINATING)
    else:
        logger.debug("%s: GPU utilization check: OK", fmt(job_model))


def _should_terminate_due_to_low_gpu_util(min_util: int, gpus_util: Iterable[Iterable[int]]):
    for gpu_util in gpus_util:
        if all(util < min_util for util in gpu_util):
            return True
    return False


def _set_disconnected_at_now(session: AsyncSession, job_model: JobModel) -> None:
    if job_model.disconnected_at is None:
        job_model.disconnected_at = common_utils.get_current_datetime()
        events.emit(
            session,
            "Job became unreachable",
            actor=events.SystemActor(),
            targets=[events.Target.from_model(job_model)],
        )


def _reset_disconnected_at(session: AsyncSession, job_model: JobModel) -> None:
    if job_model.disconnected_at is not None:
        job_model.disconnected_at = None
        events.emit(
            session,
            "Job became reachable",
            actor=events.SystemActor(),
            targets=[events.Target.from_model(job_model)],
        )


def _get_cluster_info(
    jobs: List[Job],
    replica_num: int,
    job_provisioning_data: JobProvisioningData,
    job_runtime_data: Optional[JobRuntimeData],
) -> ClusterInfo:
    job_ips = []
    for job in jobs:
        if job.job_spec.replica_num == replica_num:
            job_ips.append(
                common_utils.get_or_error(
                    job.job_submissions[-1].job_provisioning_data
                ).internal_ip
                or ""
            )
    gpus_per_job = len(job_provisioning_data.instance_type.resources.gpus)
    if job_runtime_data is not None and job_runtime_data.offer is not None:
        gpus_per_job = len(job_runtime_data.offer.instance.resources.gpus)
    cluster_info = ClusterInfo(
        job_ips=job_ips,
        master_job_ip=job_ips[0],
        gpus_per_job=gpus_per_job,
    )
    return cluster_info


def _get_repo_code_hash(run: Run, job: Job) -> Optional[str]:
    # TODO: drop this function when supporting jobs submitted before 0.19.17 is no longer relevant.
    if (
        job.job_spec.repo_code_hash is None
        and run.run_spec.repo_code_hash is not None
        and job.job_submissions[-1].deployment_num == run.deployment_num
    ):
        # The job spec does not have `repo_code_hash`, because it was submitted before 0.19.17.
        # Use `repo_code_hash` from the run.
        return run.run_spec.repo_code_hash
    return job.job_spec.repo_code_hash


async def _get_job_code(
    session: AsyncSession, project: ProjectModel, repo: RepoModel, code_hash: Optional[str]
) -> bytes:
    if code_hash is None:
        return b""
    code_model = await get_code_model(session=session, repo=repo, code_hash=code_hash)
    if code_model is None:
        return b""
    if code_model.blob is not None:
        return code_model.blob
    storage = get_default_storage()
    if storage is None:
        return b""
    blob = await common_utils.run_async(
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
    session: AsyncSession,
    archive_mappings: Iterable[FileArchiveMapping],
    user: UserModel,
) -> list[tuple[uuid.UUID, bytes]]:
    archives: list[tuple[uuid.UUID, bytes]] = []
    for archive_mapping in archive_mappings:
        archive_id = archive_mapping.id
        archive_blob = await _get_job_file_archive(
            session=session, archive_id=archive_id, user=user
        )
        archives.append((archive_id, archive_blob))
    return archives


async def _get_job_file_archive(
    session: AsyncSession, archive_id: uuid.UUID, user: UserModel
) -> bytes:
    archive_model = await files_services.get_archive_model(session, id=archive_id, user=user)
    if archive_model is None:
        return b""
    if archive_model.blob is not None:
        return archive_model.blob
    storage = get_default_storage()
    if storage is None:
        return b""
    blob = await common_utils.run_async(
        storage.get_archive,
        str(archive_model.user_id),
        archive_model.blob_hash,
    )
    if blob is None:
        logger.error("Failed to get file archive %s from storage", archive_id)
        return b""
    return blob


@runner_ssh_tunnel(ports=[DSTACK_RUNNER_HTTP_PORT], retries=1)
def _submit_job_to_runner(
    ports: Dict[int, int],
    session: AsyncSession,
    run: Run,
    job_model: JobModel,
    job: Job,
    cluster_info: ClusterInfo,
    code: bytes,
    file_archives: Iterable[tuple[uuid.UUID, bytes]],
    secrets: Dict[str, str],
    repo_credentials: Optional[RemoteRepoCreds],
    success_if_not_available: bool,
) -> bool:
    """
    Possible next states:
    - JobStatus.RUNNING if runner is available
    - JobStatus.TERMINATING if timeout is exceeded

    Returns:
        is successful
    """
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
    resp = runner_client.healthcheck()
    if resp is None:
        # runner is not available yet
        return success_if_not_available

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
        jrd = get_job_runtime_data(job_model)
        if jrd is not None:
            jrd.working_dir = job_info.working_dir
            jrd.username = job_info.username
            job_model.job_runtime_data = jrd.json()

    switch_job_status(session, job_model, JobStatus.RUNNING)
    # do not log here, because the runner will send a new status

    return True


def _interpolate_secrets(secrets: Dict[str, str], job_spec: JobSpec):
    interpolate = VariablesInterpolator({"secrets": secrets}).interpolate_or_error
    job_spec.env = {k: interpolate(v) for k, v in job_spec.env.items()}
    if job_spec.registry_auth is not None:
        job_spec.registry_auth = RegistryAuth(
            username=interpolate(job_spec.registry_auth.username),
            password=interpolate(job_spec.registry_auth.password),
        )
