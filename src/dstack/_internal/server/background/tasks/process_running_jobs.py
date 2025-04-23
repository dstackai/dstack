import asyncio
from collections.abc import Iterable
from datetime import timedelta
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.consts import DSTACK_RUNNER_HTTP_PORT, DSTACK_SHIM_HTTP_PORT
from dstack._internal.core.errors import GatewayError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import NetworkMode, RegistryAuth
from dstack._internal.core.models.configurations import DevEnvironmentConfiguration
from dstack._internal.core.models.instances import (
    InstanceStatus,
    RemoteConnectionInfo,
    SSHConnectionParams,
)
from dstack._internal.core.models.metrics import Metric
from dstack._internal.core.models.repos import RemoteRepoCreds
from dstack._internal.core.models.runs import (
    ClusterInfo,
    Job,
    JobProvisioningData,
    JobRuntimeData,
    JobSpec,
    JobStatus,
    JobTerminationReason,
    Run,
    RunSpec,
)
from dstack._internal.core.models.volumes import InstanceMountPoint, Volume, VolumeMountPoint
from dstack._internal.server.background.tasks.common import get_provisioning_timeout
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import (
    InstanceModel,
    JobModel,
    ProjectModel,
    RepoModel,
    RunModel,
)
from dstack._internal.server.schemas.runner import GPUDevice, TaskStatus
from dstack._internal.server.services import logs as logs_services
from dstack._internal.server.services import services
from dstack._internal.server.services.instances import get_instance_ssh_private_keys
from dstack._internal.server.services.jobs import (
    find_job,
    get_job_attached_volumes,
    get_job_runtime_data,
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
from dstack._internal.server.services.runs import (
    run_model_to_run,
)
from dstack._internal.server.services.storage import get_default_storage
from dstack._internal.utils import common as common_utils
from dstack._internal.utils.interpolator import VariablesInterpolator
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def process_running_jobs(batch_size: int = 1):
    tasks = []
    for _ in range(batch_size):
        tasks.append(_process_next_running_job())
    await asyncio.gather(*tasks)


async def _process_next_running_job():
    lock, lockset = get_locker().get_lockset(JobModel.__tablename__)
    async with get_session_ctx() as session:
        async with lock:
            res = await session.execute(
                select(JobModel)
                .where(
                    JobModel.status.in_(
                        [JobStatus.PROVISIONING, JobStatus.PULLING, JobStatus.RUNNING]
                    ),
                    JobModel.id.not_in(lockset),
                )
                .order_by(JobModel.last_processed_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            job_model = res.unique().scalar()
            if job_model is None:
                return
            lockset.add(job_model.id)

        try:
            job_model_id = job_model.id
            await _process_running_job(session=session, job_model=job_model)
        finally:
            lockset.difference_update([job_model_id])


async def _process_running_job(session: AsyncSession, job_model: JobModel):
    # Refetch to load related attributes.
    # joinedload produces LEFT OUTER JOIN that can't be used with FOR UPDATE.
    res = await session.execute(
        select(JobModel)
        .where(JobModel.id == job_model.id)
        .options(joinedload(JobModel.instance).joinedload(InstanceModel.project))
        .execution_options(populate_existing=True)
    )
    job_model = res.unique().scalar_one()
    res = await session.execute(
        select(RunModel)
        .where(RunModel.id == job_model.run_id)
        .options(joinedload(RunModel.project).joinedload(ProjectModel.backends))
        .options(joinedload(RunModel.user))
        .options(joinedload(RunModel.repo))
        .options(joinedload(RunModel.jobs))
    )
    run_model = res.unique().scalar_one()
    repo_model = run_model.repo
    project = run_model.project
    run = run_model_to_run(run_model, include_sensitive=True)
    job_submission = job_model_to_job_submission(job_model)
    job_provisioning_data = job_submission.job_provisioning_data
    if job_provisioning_data is None:
        logger.error("%s: job_provisioning_data of an active job is None", fmt(job_model))
        job_model.status = JobStatus.TERMINATING
        job_model.termination_reason = JobTerminationReason.TERMINATED_BY_SERVER
        job_model.last_processed_at = common_utils.get_current_datetime()
        return

    job = find_job(run.jobs, job_model.replica_num, job_model.job_num)

    # Wait until all other jobs in the replica are provisioned
    for other_job in run.jobs:
        if (
            other_job.job_spec.replica_num == job.job_spec.replica_num
            and other_job.job_submissions[-1].status == JobStatus.SUBMITTED
        ):
            job_model.last_processed_at = common_utils.get_current_datetime()
            await session.commit()
            return

    cluster_info = _get_cluster_info(
        jobs=run.jobs,
        replica_num=job.job_spec.replica_num,
        job_provisioning_data=job_provisioning_data,
        job_runtime_data=job_submission.job_runtime_data,
    )

    volumes = await get_job_attached_volumes(
        session=session,
        project=project,
        run_spec=run.run_spec,
        job_num=job.job_spec.job_num,
        job_provisioning_data=job_provisioning_data,
    )

    server_ssh_private_keys = get_instance_ssh_private_keys(
        common_utils.get_or_error(job_model.instance)
    )

    secrets = {}  # TODO secrets

    repo_creds_model = await get_repo_creds(session=session, repo=repo_model, user=run_model.user)
    repo_creds = repo_model_to_repo_head_with_creds(repo_model, repo_creds_model).repo_creds

    initial_status = job_model.status
    if initial_status == JobStatus.PROVISIONING:
        if job_provisioning_data.hostname is None:
            await _wait_for_instance_provisioning_data(job_model=job_model)
        else:
            # Wait until all other jobs in the replica have IPs assigned.
            # This is needed to ensure cluster_info has all IPs set.
            for other_job in run.jobs:
                if (
                    other_job.job_spec.replica_num == job.job_spec.replica_num
                    and other_job.job_submissions[-1].status == JobStatus.PROVISIONING
                    and other_job.job_submissions[-1].job_provisioning_data is not None
                    and other_job.job_submissions[-1].job_provisioning_data.hostname is None
                ):
                    job_model.last_processed_at = common_utils.get_current_datetime()
                    await session.commit()
                    return

            # fails are acceptable until timeout is exceeded
            if job_provisioning_data.dockerized:
                logger.debug(
                    "%s: process provisioning job with shim, age=%s",
                    fmt(job_model),
                    job_submission.age,
                )
                ssh_user = job_provisioning_data.username
                user_ssh_key = run.run_spec.ssh_key_pub.strip()
                public_keys = [project.ssh_public_key.strip(), user_ssh_key]
                if job_provisioning_data.backend == BackendType.LOCAL:
                    # No need to update ~/.ssh/authorized_keys when running shim localy
                    user_ssh_key = ""
                success = await common_utils.run_async(
                    _process_provisioning_with_shim,
                    server_ssh_private_keys,
                    job_provisioning_data,
                    None,
                    run,
                    job_model,
                    job_provisioning_data,
                    volumes,
                    secrets,
                    job.job_spec.registry_auth,
                    public_keys,
                    ssh_user,
                    user_ssh_key,
                )
            else:
                logger.debug(
                    "%s: process provisioning job without shim, age=%s",
                    fmt(job_model),
                    job_submission.age,
                )
                code = await _get_job_code(
                    session=session,
                    project=project,
                    repo=repo_model,
                    code_hash=run.run_spec.repo_code_hash,
                )
                success = await common_utils.run_async(
                    _submit_job_to_runner,
                    server_ssh_private_keys,
                    job_provisioning_data,
                    None,
                    run,
                    job_model,
                    job,
                    cluster_info,
                    code,
                    secrets,
                    repo_creds,
                    success_if_not_available=False,
                )

            if not success:
                # check timeout
                if job_submission.age > get_provisioning_timeout(
                    backend_type=job_provisioning_data.get_base_backend(),
                    instance_type_name=job_provisioning_data.instance_type.name,
                ):
                    logger.warning(
                        "%s: failed because runner has not become available in time, age=%s",
                        fmt(job_model),
                        job_submission.age,
                    )
                    job_model.status = JobStatus.TERMINATING
                    job_model.termination_reason = (
                        JobTerminationReason.WAITING_RUNNER_LIMIT_EXCEEDED
                    )
                    # instance will be emptied by process_terminating_jobs

    else:  # fails are not acceptable
        if initial_status == JobStatus.PULLING:
            logger.debug(
                "%s: process pulling job with shim, age=%s", fmt(job_model), job_submission.age
            )
            code = await _get_job_code(
                session=session,
                project=project,
                repo=repo_model,
                code_hash=run.run_spec.repo_code_hash,
            )
            success = await common_utils.run_async(
                _process_pulling_with_shim,
                server_ssh_private_keys,
                job_provisioning_data,
                None,
                run,
                job_model,
                job,
                cluster_info,
                code,
                secrets,
                repo_creds,
                server_ssh_private_keys,
                job_provisioning_data,
            )
        elif initial_status == JobStatus.RUNNING:
            logger.debug("%s: process running job, age=%s", fmt(job_model), job_submission.age)
            success = await common_utils.run_async(
                _process_running,
                server_ssh_private_keys,
                job_provisioning_data,
                job_submission.job_runtime_data,
                run_model,
                job_model,
            )
            if not success:
                job_model.termination_reason = JobTerminationReason.INTERRUPTED_BY_NO_CAPACITY

        if not success:  # kill the job
            logger.warning(
                "%s: failed because runner is not available or return an error,  age=%s",
                fmt(job_model),
                job_submission.age,
            )
            job_model.status = JobStatus.TERMINATING
            if not job_model.termination_reason:
                job_model.termination_reason = JobTerminationReason.INTERRUPTED_BY_NO_CAPACITY
            # job will be terminated and instance will be emptied by process_terminating_jobs

    if (
        initial_status != job_model.status
        and job_model.status == JobStatus.RUNNING
        and job_model.job_num == 0  # gateway connects only to the first node
        and run.run_spec.configuration.type == "service"
    ):
        ssh_head_proxy: Optional[SSHConnectionParams] = None
        ssh_head_proxy_private_key: Optional[str] = None
        instance = common_utils.get_or_error(job_model.instance)
        if instance.remote_connection_info is not None:
            rci = RemoteConnectionInfo.__response__.parse_raw(instance.remote_connection_info)
            if rci.ssh_proxy is not None:
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
                "%s: failed to register service replica: %s, age=%s",
                fmt(job_model),
                e,
                job_submission.age,
            )
            job_model.status = JobStatus.TERMINATING
            job_model.termination_reason = JobTerminationReason.GATEWAY_ERROR

    if job_model.status == JobStatus.RUNNING:
        await _check_gpu_utilization(session, job_model, job)

    job_model.last_processed_at = common_utils.get_current_datetime()
    await session.commit()


async def _wait_for_instance_provisioning_data(job_model: JobModel):
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
        job_model.status = JobStatus.TERMINATING
        # TODO use WAITING_INSTANCE_LIMIT_EXCEEDED after 0.19.x
        job_model.termination_reason = JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY
        return

    job_model.job_provisioning_data = job_model.instance.job_provisioning_data


@runner_ssh_tunnel(ports=[DSTACK_SHIM_HTTP_PORT], retries=1)
def _process_provisioning_with_shim(
    ports: Dict[int, int],
    run: Run,
    job_model: JobModel,
    job_provisioning_data: JobProvisioningData,
    volumes: List[Volume],
    secrets: Dict[str, str],
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
    job_spec = JobSpec.__response__.parse_raw(job_model.job_spec_data)

    shim_client = client.ShimClient(port=ports[DSTACK_SHIM_HTTP_PORT])

    resp = shim_client.healthcheck()
    if resp is None:
        logger.debug("%s: shim is not available yet", fmt(job_model))
        return False  # shim is not available yet

    registry_username = ""
    registry_password = ""
    if registry_auth is not None:
        logger.debug("%s: authenticating to the registry...", fmt(job_model))
        interpolate = VariablesInterpolator({"secrets": secrets}).interpolate
        registry_username = interpolate(registry_auth.username)
        registry_password = interpolate(registry_auth.password)

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

    instance_mounts += _get_instance_specific_mounts(
        job_provisioning_data.backend, job_provisioning_data.instance_type.name
    )

    gpu_devices = _get_instance_specific_gpu_devices(
        job_provisioning_data.backend, job_provisioning_data.instance_type.name
    )

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

    if shim_client.is_api_v2_supported():
        shim_client.submit_task(
            task_id=job_model.id,
            name=job_model.job_name,
            registry_username=registry_username,
            registry_password=registry_password,
            image_name=job_spec.image_name,
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
            instance_id=job_provisioning_data.instance_id,
        )
    else:
        submitted = shim_client.submit(
            username=registry_username,
            password=registry_password,
            image_name=job_spec.image_name,
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
            instance_id=job_provisioning_data.instance_id,
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

    job_model.status = JobStatus.PULLING
    logger.info("%s: now is %s", fmt(job_model), job_model.status.name)
    return True


@runner_ssh_tunnel(ports=[DSTACK_SHIM_HTTP_PORT])
def _process_pulling_with_shim(
    ports: Dict[int, int],
    run: Run,
    job_model: JobModel,
    job: Job,
    cluster_info: ClusterInfo,
    code: bytes,
    secrets: Dict[str, str],
    repo_credentials: Optional[RemoteRepoCreds],
    server_ssh_private_keys: tuple[str, Optional[str]],
    job_provisioning_data: JobProvisioningData,
) -> bool:
    """
    Possible next states:
    - JobStatus.RUNNING if runner is available
    - JobStatus.TERMINATING if shim is not available

    Returns:
        is successful
    """
    shim_client = client.ShimClient(port=ports[DSTACK_SHIM_HTTP_PORT])
    if shim_client.is_api_v2_supported():  # raises error if shim is down, causes retry
        task = shim_client.get_task(job_model.id)

        # If task goes to terminated before the job is submitted to runner, then an error occured
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
            return True

        job_runtime_data = get_job_runtime_data(job_model)
        # should check for None, as there may be older jobs submitted before
        # JobRuntimeData was introduced
        if job_runtime_data is not None:
            # port mapping is not yet available, waiting
            if task.ports is None:
                return True
            job_runtime_data.ports = {pm.container: pm.host for pm in task.ports}
            job_model.job_runtime_data = job_runtime_data.json()

    else:
        shim_status = shim_client.pull()  # raises error if shim is down, causes retry

        # If shim goes to pending before the job is submitted to runner, then an error occured
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
            return True

    return _submit_job_to_runner(
        server_ssh_private_keys,
        job_provisioning_data,
        job_runtime_data,
        run=run,
        job_model=job_model,
        job=job,
        cluster_info=cluster_info,
        code=code,
        secrets=secrets,
        repo_credentials=repo_credentials,
        success_if_not_available=True,
    )


@runner_ssh_tunnel(ports=[DSTACK_RUNNER_HTTP_PORT])
def _process_running(
    ports: Dict[int, int],
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
    previous_status = job_model.status
    if len(resp.job_states) > 0:
        latest_state_event = resp.job_states[-1]
        latest_status = latest_state_event.state
        if latest_status == JobStatus.DONE:
            job_model.status = JobStatus.TERMINATING
            job_model.termination_reason = JobTerminationReason.DONE_BY_RUNNER
        elif latest_status in {JobStatus.FAILED, JobStatus.TERMINATED}:
            job_model.status = JobStatus.TERMINATING
            job_model.termination_reason = JobTerminationReason.CONTAINER_EXITED_WITH_ERROR
            if latest_state_event.termination_reason:
                job_model.termination_reason = JobTerminationReason(
                    latest_state_event.termination_reason.lower()
                )
            if latest_state_event.termination_message:
                job_model.termination_reason_message = latest_state_event.termination_message
    else:
        _terminate_if_inactivity_duration_exceeded(run_model, job_model, resp.no_connections_secs)
    if job_model.status != previous_status:
        logger.info("%s: now is %s", fmt(job_model), job_model.status.name)
    return True


def _terminate_if_inactivity_duration_exceeded(
    run_model: RunModel, job_model: JobModel, no_connections_secs: Optional[int]
) -> None:
    conf = RunSpec.__response__.parse_raw(run_model.run_spec).configuration
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
        job_model.status = JobStatus.TERMINATING
        job_model.termination_reason = JobTerminationReason.INTERRUPTED_BY_NO_CAPACITY
        job_model.termination_reason_message = (
            "The selected instance was created before dstack 0.18.41"
            " and does not support inactivity_duration"
        )
    elif no_connections_secs >= conf.inactivity_duration:
        job_model.status = JobStatus.TERMINATING
        # TODO(0.19 or earlier): set JobTerminationReason.INACTIVITY_DURATION_EXCEEDED
        job_model.termination_reason = JobTerminationReason.TERMINATED_BY_SERVER
        job_model.termination_reason_message = (
            f"The job was inactive for {no_connections_secs} seconds,"
            f" exceeding the inactivity_duration of {conf.inactivity_duration} seconds"
        )


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
        logger.info("%s: GPU utilization check: terminating", fmt(job_model))
        job_model.status = JobStatus.TERMINATING
        # TODO(0.19 or earlier): set JobTerminationReason.TERMINATED_DUE_TO_UTILIZATION_POLICY
        job_model.termination_reason = JobTerminationReason.TERMINATED_BY_SERVER
        job_model.termination_reason_message = (
            f"The job GPU utilization below {policy.min_gpu_utilization}%"
            f" for {policy.time_window} seconds"
        )
    else:
        logger.debug("%s: GPU utilization check: OK", fmt(job_model))


def _should_terminate_due_to_low_gpu_util(min_util: int, gpus_util: Iterable[Iterable[int]]):
    for gpu_util in gpus_util:
        if all(util < min_util for util in gpu_util):
            return True
    return False


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


@runner_ssh_tunnel(ports=[DSTACK_RUNNER_HTTP_PORT], retries=1)
def _submit_job_to_runner(
    ports: Dict[int, int],
    run: Run,
    job_model: JobModel,
    job: Job,
    cluster_info: ClusterInfo,
    code: bytes,
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
    if instance is not None and instance.remote_connection_info is not None:
        remote_info = RemoteConnectionInfo.__response__.parse_raw(instance.remote_connection_info)
        instance_env = remote_info.env
    else:
        instance_env = None

    runner_client = client.RunnerClient(port=ports[DSTACK_RUNNER_HTTP_PORT])
    resp = runner_client.healthcheck()
    if resp is None:
        # runner is not available yet
        return success_if_not_available

    runner_client.submit_job(
        run_spec=run.run_spec,
        job_spec=job.job_spec,
        cluster_info=cluster_info,
        secrets=secrets,
        repo_credentials=repo_credentials,
        instance_env=instance_env,
    )
    logger.debug("%s: uploading code", fmt(job_model))
    runner_client.upload_code(code)
    logger.debug("%s: starting job", fmt(job_model))
    runner_client.run_job()

    job_model.status = JobStatus.RUNNING
    # do not log here, because the runner will send a new status

    return True


def _get_instance_specific_mounts(
    backend_type: BackendType, instance_type_name: str
) -> List[InstanceMountPoint]:
    if backend_type == BackendType.GCP:
        if instance_type_name == "a3-megagpu-8g":
            return [
                InstanceMountPoint(
                    instance_path="/dev/aperture_devices",
                    path="/dev/aperture_devices",
                ),
                InstanceMountPoint(
                    instance_path="/var/lib/tcpxo/lib64",
                    path="/var/lib/tcpxo/lib64",
                ),
                InstanceMountPoint(
                    instance_path="/var/lib/fastrak/lib64",
                    path="/var/lib/fastrak/lib64",
                ),
            ]
        if instance_type_name in ["a3-edgegpu-8g", "a3-highgpu-8g"]:
            return [
                InstanceMountPoint(
                    instance_path="/var/lib/nvidia/lib64",
                    path="/usr/local/nvidia/lib64",
                ),
                InstanceMountPoint(
                    instance_path="/var/lib/nvidia/bin",
                    path="/usr/local/nvidia/bin",
                ),
                InstanceMountPoint(
                    instance_path="/var/lib/tcpx/lib64",
                    path="/usr/local/tcpx/lib64",
                ),
                InstanceMountPoint(
                    instance_path="/run/tcpx",
                    path="/run/tcpx",
                ),
            ]
    return []


def _get_instance_specific_gpu_devices(
    backend_type: BackendType, instance_type_name: str
) -> List[GPUDevice]:
    gpu_devices = []
    if backend_type == BackendType.GCP and instance_type_name in [
        "a3-edgegpu-8g",
        "a3-highgpu-8g",
    ]:
        for i in range(8):
            gpu_devices.append(
                GPUDevice(path_on_host=f"/dev/nvidia{i}", path_in_container=f"/dev/nvidia{i}")
            )
        gpu_devices.append(
            GPUDevice(path_on_host="/dev/nvidia-uvm", path_in_container="/dev/nvidia-uvm")
        )
        gpu_devices.append(
            GPUDevice(path_on_host="/dev/nvidiactl", path_in_container="/dev/nvidiactl")
        )
    return gpu_devices
