import asyncio
import itertools
import math
import re
import uuid
from datetime import timezone
from typing import List, Optional, Tuple, cast

import pydantic
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

import dstack._internal.server.services.gateways as gateways
import dstack._internal.utils.common as common_utils
from dstack._internal.core.backends.base import Backend
from dstack._internal.core.errors import (
    BackendError,
    RepoDoesNotExistError,
    ServerClientError,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    DockerConfig,
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOfferWithAvailability,
    InstanceRuntime,
    LaunchedInstanceInfo,
    SSHKey,
)
from dstack._internal.core.models.pools import Instance
from dstack._internal.core.models.profiles import CreationPolicy, Profile
from dstack._internal.core.models.runs import (
    InstanceStatus,
    Job,
    JobPlan,
    JobProvisioningData,
    JobSpec,
    JobStatus,
    JobSubmission,
    JobTerminationReason,
    Requirements,
    Run,
    RunPlan,
    RunSpec,
    RunStatus,
    RunTerminationReason,
    ServiceInfo,
    ServiceModelInfo,
)
from dstack._internal.core.models.users import GlobalRole
from dstack._internal.server.models import (
    InstanceModel,
    JobModel,
    ProjectModel,
    RunModel,
    UserModel,
)
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services import pools as pools_services
from dstack._internal.server.services import repos as repos_services
from dstack._internal.server.services.docker import parse_image_name
from dstack._internal.server.services.gateways.options import (
    complete_service_model,
    get_service_options,
)
from dstack._internal.server.services.jobs import (
    PROCESSING_RUNS_IDS,
    PROCESSING_RUNS_LOCK,
    RUNNING_PROCESSING_JOBS_IDS,
    RUNNING_PROCESSING_JOBS_LOCK,
    get_jobs_from_run_spec,
    job_model_to_job_submission,
    process_terminating_job,
    stop_runner,
)
from dstack._internal.server.services.jobs.configurators.base import (
    get_default_image,
    get_default_python_verison,
)
from dstack._internal.server.services.pools import (
    filter_pool_instances,
    get_or_create_pool_by_name,
    get_pool_instances,
    instance_model_to_instance,
)
from dstack._internal.server.services.projects import list_project_models, list_user_project_models
from dstack._internal.server.utils.common import run_async
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.random_names import generate_name

BACKENDS_WITH_CREATE_INSTANCE_SUPPORT = [
    BackendType.AWS,
    BackendType.DATACRUNCH,
    BackendType.GCP,
]

logger = get_logger(__name__)


async def list_user_runs(
    session: AsyncSession,
    user: UserModel,
    project_name: Optional[str],
    repo_id: Optional[str],
) -> List[Run]:
    if user.global_role == GlobalRole.ADMIN:
        projects = await list_project_models(session=session)
    else:
        projects = await list_user_project_models(session=session, user=user)
    if project_name:
        projects = [p for p in projects if p.name == project_name]
    runs = []
    for project in projects:
        project_runs = await list_project_runs(
            session=session,
            project=project,
            repo_id=repo_id,
        )
        runs.extend(project_runs)
    return sorted(runs, key=lambda r: r.submitted_at, reverse=True)


async def list_project_runs(
    session: AsyncSession,
    project: ProjectModel,
    repo_id: Optional[str],
) -> List[Run]:
    filters = [
        RunModel.project_id == project.id,
        RunModel.deleted == False,
    ]
    if repo_id is not None:
        repo = await repos_services.get_repo_model(
            session=session,
            project=project,
            repo_id=repo_id,
        )
        if repo is None:
            raise RepoDoesNotExistError.with_id(repo_id)
        filters.append(RunModel.repo_id == repo.id)
    res = await session.execute(
        select(RunModel).where(*filters).options(joinedload(RunModel.user))
    )
    run_models = res.scalars().all()
    runs = []
    for r in run_models:
        try:
            runs.append(run_model_to_run(r))
        except pydantic.ValidationError:
            pass
    if len(run_models) > len(runs):
        logger.debug(
            "Can't load %s runs from project %s", len(run_models) - len(runs), project.name
        )
    return runs


async def get_run(
    session: AsyncSession,
    project: ProjectModel,
    run_name: str,
) -> Optional[Run]:
    res = await session.execute(
        select(RunModel)
        .where(
            RunModel.project_id == project.id,
            RunModel.run_name == run_name,
            RunModel.deleted == False,
        )
        .options(joinedload(RunModel.user))
    )
    run_model = res.scalar()
    if run_model is None:
        return None
    return run_model_to_run(run_model)


async def get_run_plan(
    session: AsyncSession, project: ProjectModel, user: UserModel, run_spec: RunSpec
) -> RunPlan:
    if run_spec.run_name is not None:
        _validate_run_name(run_spec.run_name)

    profile = run_spec.profile
    creation_policy = profile.creation_policy

    pool = await get_or_create_pool_by_name(
        session=session, project=project, pool_name=profile.pool_name
    )
    pool_filtered_instances = filter_pool_instances(
        pool_instances=get_pool_instances(pool),
        profile=profile,
        resources=run_spec.configuration.resources,
    )
    pool_offers: List[InstanceOfferWithAvailability] = []
    for instance in pool_filtered_instances:
        offer = InstanceOfferWithAvailability.parse_raw(instance.offer)
        offer.availability = InstanceAvailability.BUSY
        if instance.status == InstanceStatus.READY:
            offer.availability = InstanceAvailability.READY
        pool_offers.append(offer)

    run_name = run_spec.run_name  # preserve run_name
    run_spec.run_name = "dry-run"  # will regenerate jobs on submission
    jobs = get_jobs_from_run_spec(run_spec)
    job_plans = []

    for job in jobs:
        job_offers: List[InstanceOfferWithAvailability] = []
        job_offers.extend(pool_offers)

        if creation_policy is None or creation_policy == CreationPolicy.REUSE_OR_CREATE:
            offers = await get_offers_by_requirements(
                project=project,
                profile=profile,
                requirements=job.job_spec.requirements,
                exclude_not_available=False,
            )
            job_offers.extend(offer for _, offer in offers)

        # TODO(egor-s): merge job_offers and pool_offers based on (availability, use/create, price)
        job_plan = JobPlan(
            job_spec=job.job_spec,
            offers=job_offers[:50],
            total_offers=len(job_offers),
            max_price=max((offer.price for offer in job_offers), default=None),
        )
        job_plans.append(job_plan)

    run_spec.profile.pool_name = pool.name  # write pool name back for the client
    run_spec.run_name = run_name  # restore run_name
    run_plan = RunPlan(
        project_name=project.name, user=user.name, run_spec=run_spec, job_plans=job_plans
    )
    return run_plan


async def get_offers_by_requirements(
    project: ProjectModel,
    profile: Profile,
    requirements: Requirements,
    exclude_not_available=False,
) -> List[Tuple[Backend, InstanceOfferWithAvailability]]:
    backends: List[Backend] = await backends_services.get_project_backends(project=project)

    if profile.backends is not None:
        backends = [b for b in backends if b.TYPE in profile.backends]

    offers = await backends_services.get_instance_offers(
        backends=backends,
        requirements=requirements,
        exclude_not_available=exclude_not_available,
    )

    # Hide internal offer.backend by backend that returned the offer.
    # This is relevant for dstack Cloud.
    for backend, offer in offers:
        offer.backend = backend.TYPE

    return offers


async def submit_run(
    session: AsyncSession,
    user: UserModel,
    project: ProjectModel,
    run_spec: RunSpec,
) -> Run:
    repo = await repos_services.get_repo_model(
        session=session,
        project=project,
        repo_id=run_spec.repo_id,
    )
    if repo is None:
        raise RepoDoesNotExistError.with_id(run_spec.repo_id)

    backends = await backends_services.get_project_backends(project)
    if len(backends) == 0:
        raise ServerClientError("No backends configured")

    if run_spec.run_name is None:
        run_spec.run_name = await _generate_run_name(
            session=session,
            project=project,
        )
    else:
        _validate_run_name(run_spec.run_name)
        await delete_runs(session=session, project=project, runs_names=[run_spec.run_name])

    pool = await get_or_create_pool_by_name(session, project, run_spec.profile.pool_name)

    submitted_at = common_utils.get_current_datetime()
    run_model = RunModel(
        id=uuid.uuid4(),
        project_id=project.id,
        project=project,
        repo_id=repo.id,
        user_id=user.id,
        run_name=run_spec.run_name,
        submitted_at=submitted_at,
        status=RunStatus.SUBMITTED,
        run_spec=run_spec.json(),
        last_processed_at=submitted_at,
    )
    session.add(run_model)

    if run_spec.configuration.type == "service":
        if run_spec.configuration.model is not None:
            complete_service_model(run_spec.configuration.model)
            run_model.run_spec = run_spec.json()
        await gateways.register_service(
            session, run_model, get_service_options(run_spec.configuration)
        )

    jobs = get_jobs_from_run_spec(run_spec)
    for job in jobs:
        job.job_spec.pool_name = pool.name
        job_model = create_job_model_for_new_submission(
            run_model=run_model,
            job=job,
            status=JobStatus.SUBMITTED,
        )
        session.add(job_model)
    await session.commit()
    await session.refresh(run_model)

    run = run_model_to_run(run_model)
    return run


def create_job_model_for_new_submission(
    run_model: RunModel,
    job: Job,
    status: JobStatus,
) -> JobModel:
    now = common_utils.get_current_datetime()
    return JobModel(
        id=uuid.uuid4(),
        project_id=run_model.project_id,
        run_id=run_model.id,
        run_name=run_model.run_name,
        job_num=job.job_spec.job_num,
        job_name=job.job_spec.job_name,
        replica_num=0,  # TODO(egor-s): replace with actual replica number
        submission_num=len(job.job_submissions),
        submitted_at=now,
        last_processed_at=now,
        status=status,
        termination_reason=None,
        job_spec_data=job.job_spec.json(),
        job_provisioning_data=None,
    )


async def stop_runs(
    session: AsyncSession,
    project: ProjectModel,
    runs_names: List[str],
    abort: bool,
):
    """
    If abort is False, jobs receive a signal to stop and run status will be changed as a reaction to jobs status change.
    If abort is True, run is marked as TERMINATED and process_runs will stop the jobs.
    """
    res = await session.execute(
        select(RunModel).where(
            RunModel.project_id == project.id,
            RunModel.run_name.in_(runs_names),
            RunModel.status.not_in(RunStatus.finished_statuses()),
        )
    )
    runs = res.scalars().all()
    # TODO(egor-s): consider raising an exception if no runs found
    await asyncio.gather(*(stop_run(session, run, abort) for run in runs))


async def stop_run(session: AsyncSession, run: RunModel, abort: bool):
    while True:
        async with PROCESSING_RUNS_LOCK:
            if run.id not in PROCESSING_RUNS_IDS:
                PROCESSING_RUNS_IDS.add(run.id)
                break
        await asyncio.sleep(0.1)

    try:
        await session.refresh(run)
        if run.status.is_finished():
            return

        run.status = RunStatus.TERMINATING
        if abort:
            run.termination_reason = RunTerminationReason.ABORTED_BY_USER
        else:
            run.termination_reason = RunTerminationReason.STOPPED_BY_USER
        await session.commit()  # run will be refreshed later
        # process the run out of turn
        await process_terminating_run(session, run)

        run.last_processed_at = common_utils.get_current_datetime()
        await session.commit()
    finally:
        PROCESSING_RUNS_IDS.remove(run.id)


async def delete_runs(
    session: AsyncSession,
    project: ProjectModel,
    runs_names: List[str],
):
    res = await session.execute(
        select(RunModel).where(
            RunModel.project_id == project.id, RunModel.run_name.in_(runs_names)
        )
    )
    run_models = res.scalars().all()
    active_runs = [r for r in run_models if not r.processing_finished]
    if len(active_runs) > 0:
        raise ServerClientError(
            msg=f"Cannot delete active runs: {[r.run_name for r in active_runs]}"
        )
    await session.execute(
        update(RunModel)
        .where(
            RunModel.project_id == project.id,
            RunModel.run_name.in_(runs_names),
        )
        .values(deleted=True)
    )
    await session.commit()


async def get_create_instance_offers(
    project: ProjectModel,
    profile: Profile,
    requirements: Requirements,
    exclude_not_available=False,
) -> List[Tuple[Backend, InstanceOfferWithAvailability]]:
    offers = await get_offers_by_requirements(
        project=project,
        profile=profile,
        requirements=requirements,
        exclude_not_available=exclude_not_available,
    )
    offers = [
        (backend, offer)
        for backend, offer in offers
        if backend.TYPE in BACKENDS_WITH_CREATE_INSTANCE_SUPPORT
    ]
    return offers


async def create_instance(
    session: AsyncSession,
    project: ProjectModel,
    user: UserModel,
    ssh_key: SSHKey,
    pool_name: str,
    instance_name: str,
    profile: Profile,
    requirements: Requirements,
) -> Instance:
    offers = await get_create_instance_offers(
        project=project,
        profile=profile,
        requirements=requirements,
        exclude_not_available=True,
    )

    # Raise error if no backends suppport create_instance
    backend_types = set((backend.TYPE for backend, _ in offers))
    if all(
        (backend_type not in BACKENDS_WITH_CREATE_INSTANCE_SUPPORT)
        for backend_type in backend_types
    ):
        backends = ", ".join(sorted(backend_types))
        raise ServerClientError(
            f"Backends {backends} do not support create_intance. Try to select other backends."
        )

    pool = await pools_services.get_or_create_pool_by_name(session, project, pool_name)

    user_ssh_key = ssh_key
    project_ssh_key = SSHKey(
        public=project.ssh_public_key.strip(),
        private=project.ssh_private_key.strip(),
    )
    image = parse_image_name(get_default_image(get_default_python_verison()))
    instance_config = InstanceConfiguration(
        project_name=project.name,
        instance_name=instance_name,
        ssh_keys=[user_ssh_key, project_ssh_key],
        job_docker_config=DockerConfig(
            image=image,
            registry_auth=None,
        ),
        user=user.name,
    )

    for backend, instance_offer in offers:
        # cannot create an instance in vastai/k8s. skip
        if instance_offer.instance_runtime == InstanceRuntime.RUNNER:
            continue
        logger.debug(
            "trying %s in %s/%s for $%0.4f per hour",
            instance_offer.instance.name,
            instance_offer.backend.value,
            instance_offer.region,
            instance_offer.price,
        )
        try:
            launched_instance_info: LaunchedInstanceInfo = await run_async(
                backend.compute().create_instance,
                instance_offer,
                instance_config,
            )
        except BackendError as e:
            logger.warning(
                "%s launch in %s/%s failed: %s",
                instance_offer.instance.name,
                instance_offer.backend.value,
                instance_offer.region,
                repr(e),
            )
            continue
        except NotImplementedError:
            # skip a backend without create_instance support, continue with next backend and offer
            continue
        job_provisioning_data = JobProvisioningData(
            backend=backend.TYPE,
            instance_type=instance_offer.instance,
            instance_id=launched_instance_info.instance_id,
            hostname=launched_instance_info.ip_address,
            region=launched_instance_info.region,
            price=instance_offer.price,
            username=launched_instance_info.username,
            ssh_port=launched_instance_info.ssh_port,
            dockerized=launched_instance_info.dockerized,
            backend_data=launched_instance_info.backend_data,
            ssh_proxy=None,
        )
        im = InstanceModel(
            name=instance_name,
            project=project,
            pool=pool,
            created_at=common_utils.get_current_datetime(),
            started_at=common_utils.get_current_datetime(),
            status=InstanceStatus.STARTING,
            backend=backend.TYPE,
            region=instance_offer.region,
            price=instance_offer.price,
            job_provisioning_data=job_provisioning_data.json(),
            offer=cast(InstanceOfferWithAvailability, instance_offer).json(),
            termination_policy=profile.termination_policy,
            termination_idle_time=profile.termination_idle_time,
        )
        session.add(im)
        await session.commit()
        return instance_model_to_instance(im)
    raise ServerClientError("Failed to find offers to create the instance.")


def run_model_to_run(run_model: RunModel, include_job_submissions: bool = True) -> Run:
    jobs: List[Job] = []
    # JobSpec from JobConfigurator doesn't have gateway information for `service` type
    # TODO(egor-s): consider replicas
    run_jobs = sorted(run_model.jobs, key=lambda j: (j.job_num, j.submission_num))
    for job_num, job_submissions in itertools.groupby(run_jobs):
        job_spec = None
        submissions = []
        for job_model in job_submissions:
            if job_spec is None:
                job_spec = JobSpec.parse_raw(job_model.job_spec_data)
            if include_job_submissions:
                submissions.append(job_model_to_job_submission(job_model))
        if job_spec is not None:
            jobs.append(Job(job_spec=job_spec, job_submissions=submissions))

    run_spec = RunSpec.parse_raw(run_model.run_spec)

    latest_job_submission = None
    if include_job_submissions:
        latest_job_submission = jobs[0].job_submissions[-1]

    run = Run(
        id=run_model.id,
        project_name=run_model.project.name,
        user=run_model.user.name,
        submitted_at=run_model.submitted_at.replace(tzinfo=timezone.utc),
        status=run_model.status,
        run_spec=run_spec,
        jobs=jobs,
        latest_job_submission=latest_job_submission,
    )
    # TODO(egor-s): add replicas support
    run.cost = _get_run_cost(run)
    run.service = _get_run_service(run)
    return run


_PROJECTS_TO_RUN_NAMES_LOCK = {}


async def _generate_run_name(
    session: AsyncSession,
    project: ProjectModel,
) -> str:
    lock = _PROJECTS_TO_RUN_NAMES_LOCK.setdefault(project.name, asyncio.Lock())
    run_name_base = generate_name()
    idx = 1
    async with lock:
        while (
            await get_run(
                session=session,
                project=project,
                run_name=f"{run_name_base}-{idx}",
            )
            is not None
        ):
            idx += 1
        return f"{run_name_base}-{idx}"


def _get_run_cost(run: Run) -> float:
    run_cost = math.fsum(
        _get_job_submission_cost(submission)
        for job in run.jobs
        for submission in job.job_submissions
    )
    return round(run_cost, 4)


def _get_job_submission_cost(job_submission: JobSubmission) -> float:
    if job_submission.job_provisioning_data is None:
        return 0
    duration_hours = job_submission.duration.total_seconds() / 3600
    return job_submission.job_provisioning_data.price * duration_hours


def _get_run_service(run: Run) -> Optional[ServiceInfo]:
    if run.run_spec.configuration.type != "service":
        return None

    gateway = run.jobs[0].job_spec.gateway
    model = None
    if run.run_spec.configuration.model is not None:
        domain = gateway.hostname.split(".", maxsplit=1)[1]
        model = ServiceModelInfo(
            name=run.run_spec.configuration.model.name,
            base_url=f"https://gateway.{domain}",
            type=run.run_spec.configuration.model.type,
        )

    omit_port = (gateway.secure and gateway.public_port == 443) or (
        not gateway.secure and gateway.public_port == 80
    )
    return ServiceInfo(
        url="%s://%s%s"
        % (
            "https" if gateway.secure else "http",
            gateway.hostname,
            "" if omit_port else f":{gateway.public_port}",
        ),
        model=model,
    )


# The run_name validation is not performed in pydantic models since
# the models are reused on the client, and we don't want to
# tie run_name validation to the client side.
def _validate_run_name(run_name: str):
    if not re.match("^[a-z][a-z0-9-]{1,40}$", run_name):
        raise ServerClientError("run_name should match regex '^[a-z][a-z0-9-]{1,40}$'")


async def process_terminating_run(session: AsyncSession, run: RunModel):
    """
    Used by both `process_runs` and `stop_run` to process a run that is TERMINATING.
    Caller must acquire the lock on run.
    """
    job_termination_reason = run_to_job_termination_reason(run.termination_reason)

    jobs_ids_set = {job.id for job in run.jobs}
    while True:  # let job processing complete
        # TODO(egor-s): acquire locks for submitted and terminating jobs
        async with RUNNING_PROCESSING_JOBS_LOCK:
            if not RUNNING_PROCESSING_JOBS_IDS & jobs_ids_set:
                break
            await asyncio.sleep(0.1)
    await session.refresh(run)

    unfinished_jobs_count = 0
    job: JobModel
    for job in run.jobs:
        if job.status.is_finished():
            continue
        unfinished_jobs_count += 1
        if job.status == JobStatus.TERMINATING:
            # `process_terminating_jobs` will abort frozen jobs
            continue

        if job.status == JobStatus.RUNNING and job_termination_reason not in {
            JobTerminationReason.ABORTED_BY_USER,
            JobTerminationReason.DONE_BY_RUNNER,
        }:
            # send a signal to stop the job gracefully
            await stop_runner(session, job)
        job.status = JobStatus.TERMINATING
        job.termination_reason = job_termination_reason
        await process_terminating_job(session, job)
        if job.status.is_finished():
            unfinished_jobs_count -= 1
        job.last_processed_at = common_utils.get_current_datetime()

    if unfinished_jobs_count == 0:
        # TODO(egor-s): unregister service
        run.status = run_termination_reason_to_status(run.termination_reason)
        logger.info(
            "%s: run status has changed TERMINATING -> %s, reason: %s",
            fmt(run),
            run.status.name,
            run.termination_reason.name,
        )


def fmt(run: RunModel) -> str:
    """Format a run for logging"""
    return f"({run.id.hex[:6]}){run.run_name}"


def run_to_job_termination_reason(
    run_termination_reason: RunTerminationReason,
) -> JobTerminationReason:
    mapping = {
        RunTerminationReason.ALL_JOBS_DONE: JobTerminationReason.DONE_BY_RUNNER,
        RunTerminationReason.JOB_FAILED: JobTerminationReason.TERMINATED_BY_SERVER,
        RunTerminationReason.RETRY_LIMIT_EXCEEDED: JobTerminationReason.TERMINATED_BY_SERVER,
        RunTerminationReason.STOPPED_BY_USER: JobTerminationReason.TERMINATED_BY_USER,
        RunTerminationReason.ABORTED_BY_USER: JobTerminationReason.ABORTED_BY_USER,
    }
    return mapping[run_termination_reason]


def run_termination_reason_to_status(run_termination_reason: RunTerminationReason) -> RunStatus:
    mapping = {
        RunTerminationReason.ALL_JOBS_DONE: RunStatus.DONE,
        RunTerminationReason.JOB_FAILED: RunStatus.FAILED,
        RunTerminationReason.RETRY_LIMIT_EXCEEDED: RunStatus.FAILED,
        RunTerminationReason.STOPPED_BY_USER: RunStatus.TERMINATED,
        RunTerminationReason.ABORTED_BY_USER: RunStatus.TERMINATED,
    }
    return mapping[run_termination_reason]
