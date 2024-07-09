import asyncio
import itertools
import math
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Set, Tuple

import pydantic
from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

import dstack._internal.server.services.gateways as gateways
import dstack._internal.utils.common as common_utils
from dstack._internal.core.backends import (
    BACKENDS_WITH_CREATE_INSTANCE_SUPPORT,
    BACKENDS_WITH_MULTINODE_SUPPORT,
)
from dstack._internal.core.backends.base import Backend
from dstack._internal.core.errors import (
    RepoDoesNotExistError,
    ResourceNotExistsError,
    ServerClientError,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    DockerConfig,
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOfferWithAvailability,
    SSHKey,
)
from dstack._internal.core.models.pools import Instance
from dstack._internal.core.models.profiles import (
    DEFAULT_POOL_TERMINATION_IDLE_TIME,
    CreationPolicy,
    Profile,
    SpotPolicy,
    TerminationPolicy,
)
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
    ServiceSpec,
    get_policy_map,
)
from dstack._internal.core.models.users import GlobalRole
from dstack._internal.core.models.volumes import Volume, VolumeStatus
from dstack._internal.core.services import validate_dstack_resource_name
from dstack._internal.server.models import (
    InstanceModel,
    JobModel,
    PoolModel,
    ProjectModel,
    RepoModel,
    RunModel,
    UserModel,
    VolumeModel,
)
from dstack._internal.server.services import backends as backends_services
from dstack._internal.server.services import pools as pools_services
from dstack._internal.server.services import repos as repos_services
from dstack._internal.server.services import volumes as volumes_services
from dstack._internal.server.services.docker import is_valid_docker_volume_target, parse_image_name
from dstack._internal.server.services.jobs import (
    RUNNING_PROCESSING_JOBS_IDS,
    RUNNING_PROCESSING_JOBS_LOCK,
    SUBMITTED_PROCESSING_JOBS_IDS,
    SUBMITTED_PROCESSING_JOBS_LOCK,
    TERMINATING_PROCESSING_JOBS_IDS,
    TERMINATING_PROCESSING_JOBS_LOCK,
    get_jobs_from_run_spec,
    group_jobs_by_replica_latest,
    job_model_to_job_submission,
    process_terminating_job,
    stop_runner,
)
from dstack._internal.server.services.jobs.configurators.base import (
    get_default_image,
    get_default_python_verison,
)
from dstack._internal.server.services.logging import fmt
from dstack._internal.server.services.pools import (
    filter_pool_instances,
    generate_instance_name,
    get_instance_offer,
    get_or_create_pool_by_name,
    get_pool_instances,
    instance_model_to_instance,
)
from dstack._internal.server.services.projects import list_project_models, list_user_project_models
from dstack._internal.server.services.users import get_user_model_by_name
from dstack._internal.server.utils.common import wait_to_lock, wait_unlock
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.random_names import generate_name

logger = get_logger(__name__)

# Run processing task must acquire the lock and add the run id to the set.
# Run processing has higher priority than job processing.
# It means that job processing tasks should not take the job if `job.run_id` is in the set.
# But run processing tasks should wait until job processing tasks release PROCESSING_JOBS locks.
PROCESSING_RUNS_LOCK = asyncio.Lock()
PROCESSING_RUNS_IDS: Set[uuid.UUID] = set()

JOB_TERMINATION_REASONS_TO_RETRY = {
    JobTerminationReason.INTERRUPTED_BY_NO_CAPACITY,
    JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY,
}


async def list_user_runs(
    session: AsyncSession,
    user: UserModel,
    project_name: Optional[str],
    repo_id: Optional[str],
    username: Optional[str],
    only_active: bool,
    prev_submitted_at: Optional[datetime],
    prev_run_id: Optional[uuid.UUID],
    limit: int,
    ascending: bool,
) -> List[Run]:
    if project_name is None and repo_id is not None:
        return []
    if user.global_role == GlobalRole.ADMIN:
        projects = await list_project_models(session=session)
    else:
        projects = await list_user_project_models(session=session, user=user)
    runs_user = None
    if username is not None:
        runs_user = await get_user_model_by_name(session=session, username=username)
        if runs_user is None:
            raise ResourceNotExistsError("User not found")
    repo = None
    if project_name is not None:
        projects = [p for p in projects if p.name == project_name]
        if len(projects) == 0:
            return []
        if repo_id is not None:
            repo = await repos_services.get_repo_model(
                session=session,
                project=projects[0],
                repo_id=repo_id,
            )
            if repo is None:
                raise RepoDoesNotExistError.with_id(repo_id)
    run_models = await list_projects_run_models(
        session=session,
        projects=projects,
        repo=repo,
        runs_user=runs_user,
        only_active=only_active,
        prev_submitted_at=prev_submitted_at,
        prev_run_id=prev_run_id,
        limit=limit,
        ascending=ascending,
    )
    runs = []
    for r in run_models:
        try:
            runs.append(run_model_to_run(r, return_in_api=True))
        except pydantic.ValidationError:
            pass
    if len(run_models) > len(runs):
        logger.debug("Can't load %s runs", len(run_models) - len(runs))
    return runs


async def list_projects_run_models(
    session: AsyncSession,
    projects: List[ProjectModel],
    repo: Optional[RepoModel],
    runs_user: Optional[UserModel],
    only_active: bool,
    prev_submitted_at: Optional[datetime],
    prev_run_id: Optional[uuid.UUID],
    limit: int,
    ascending: bool,
) -> List[RunModel]:
    filters = [RunModel.deleted == False, RunModel.project_id.in_(p.id for p in projects)]
    if repo is not None:
        filters.append(RunModel.repo_id == repo.id)
    if runs_user is not None:
        filters.append(RunModel.user_id == runs_user.id)
    if only_active:
        filters.append(RunModel.status.not_in(RunStatus.finished_statuses()))
    if prev_submitted_at is not None:
        if ascending:
            if prev_run_id is None:
                filters.append(RunModel.submitted_at > prev_submitted_at)
            else:
                filters.append(
                    or_(
                        RunModel.submitted_at > prev_submitted_at,
                        and_(
                            RunModel.submitted_at == prev_submitted_at, RunModel.id < prev_run_id
                        ),
                    )
                )
        else:
            if prev_run_id is None:
                filters.append(RunModel.submitted_at < prev_submitted_at)
            else:
                filters.append(
                    or_(
                        RunModel.submitted_at < prev_submitted_at,
                        and_(
                            RunModel.submitted_at == prev_submitted_at, RunModel.id > prev_run_id
                        ),
                    )
                )
    order_by = (RunModel.submitted_at.desc(), RunModel.id)
    if ascending:
        order_by = (RunModel.submitted_at.asc(), RunModel.id.desc())

    res = await session.execute(
        select(RunModel)
        .where(*filters)
        .order_by(*order_by)
        .limit(limit)
        .options(joinedload(RunModel.user))
    )
    run_models = list(res.scalars().all())
    return run_models


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
    return run_model_to_run(run_model, return_in_api=True)


async def get_run_plan(
    session: AsyncSession,
    project: ProjectModel,
    user: UserModel,
    run_spec: RunSpec,
) -> RunPlan:
    _validate_run_spec(run_spec)

    profile = run_spec.merged_profile
    creation_policy = profile.creation_policy

    # TODO(egor-s): do we need to generate all replicas here?
    jobs = await get_jobs_from_run_spec(run_spec, replica_num=0)

    volumes = await get_run_volumes(
        session=session,
        project=project,
        run_spec=run_spec,
    )

    pool = await get_or_create_pool_by_name(
        session=session, project=project, pool_name=profile.pool_name
    )
    pool_offers = _get_pool_offers(
        pool=pool,
        run_spec=run_spec,
        job=jobs[0],
        volumes=volumes,
    )
    run_name = run_spec.run_name  # preserve run_name
    run_spec.run_name = "dry-run"  # will regenerate jobs on submission

    # Get offers once for all jobs
    offers = []
    if creation_policy == CreationPolicy.REUSE_OR_CREATE:
        offers = await get_offers_by_requirements(
            project=project,
            profile=profile,
            requirements=jobs[0].job_spec.requirements,
            exclude_not_available=False,
            multinode=jobs[0].job_spec.jobs_per_replica > 1,
            volumes=volumes,
        )

    job_plans = []
    for job in jobs:
        job_offers: List[InstanceOfferWithAvailability] = []
        job_offers.extend(pool_offers)
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
        project_name=project.name,
        user=user.name,
        run_spec=run_spec,
        job_plans=job_plans,
    )
    return run_plan


async def get_offers_by_requirements(
    project: ProjectModel,
    profile: Profile,
    requirements: Requirements,
    exclude_not_available=False,
    multinode: bool = False,
    master_job_provisioning_data: Optional[JobProvisioningData] = None,
    volumes: Optional[List[Volume]] = None,
) -> List[Tuple[Backend, InstanceOfferWithAvailability]]:
    backends: List[Backend] = await backends_services.get_project_backends(project=project)

    # For backward-compatibility to show offers if users set `backends: [dstack]`
    if (
        profile.backends is not None
        and len(profile.backends) == 1
        and BackendType.DSTACK in profile.backends
    ):
        profile.backends = None

    backend_types = profile.backends
    regions = profile.regions

    if volumes:
        volume = volumes[0]
        backend_types = [volume.configuration.backend]
        regions = [volume.configuration.region]

    if multinode:
        if not backend_types:
            backend_types = BACKENDS_WITH_MULTINODE_SUPPORT
        backend_types = [b for b in backend_types if b in BACKENDS_WITH_MULTINODE_SUPPORT]

    # For multi-node, restrict backend and region.
    # The default behavior is to provision all nodes in the same backend and region.
    if master_job_provisioning_data is not None:
        if not backend_types:
            backend_types = [master_job_provisioning_data.backend]
        if not regions:
            regions = [master_job_provisioning_data.region]
        backend_types = [b for b in backend_types if b == master_job_provisioning_data.backend]
        regions = [b for b in backend_types if b == master_job_provisioning_data.region]

    if backend_types is not None:
        backends = [b for b in backends if b.TYPE in backend_types or b.TYPE == BackendType.DSTACK]

    offers = await backends_services.get_instance_offers(
        backends=backends,
        requirements=requirements,
        exclude_not_available=exclude_not_available,
    )

    # Filter offers again for backends since a backend
    # can return offers of different backend types (e.g. BackendType.DSTACK).
    # The first filter should remain as an optimization.
    if backend_types is not None:
        offers = [(b, o) for b, o in offers if o.backend in backend_types]

    if regions is not None:
        offers = [(b, o) for b, o in offers if o.region in regions]

    if profile.instance_types is not None:
        offers = [(b, o) for b, o in offers if o.instance.name in profile.instance_types]

    return offers


async def submit_run(
    session: AsyncSession,
    user: UserModel,
    project: ProjectModel,
    run_spec: RunSpec,
) -> Run:
    _validate_run_spec(run_spec)

    repo = await repos_services.get_repo_model(
        session=session,
        project=project,
        repo_id=run_spec.repo_id,
    )
    if repo is None:
        raise RepoDoesNotExistError.with_id(run_spec.repo_id)

    if run_spec.run_name is None:
        run_spec.run_name = await _generate_run_name(
            session=session,
            project=project,
        )
    else:
        await delete_runs(session=session, project=project, runs_names=[run_spec.run_name])

    await validate_run(
        session=session,
        user=user,
        project=project,
        run_spec=run_spec,
    )

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

    replicas = 1
    if run_spec.configuration.type == "service":
        replicas = run_spec.configuration.replicas.min
        await gateways.register_service(session, run_model)

    for replica_num in range(replicas):
        jobs = await get_jobs_from_run_spec(run_spec, replica_num=replica_num)
        for job in jobs:
            job_model = create_job_model_for_new_submission(
                run_model=run_model,
                job=job,
                status=JobStatus.SUBMITTED,
            )
            session.add(job_model)
    await session.commit()
    await session.refresh(run_model)

    run = run_model_to_run(run_model, return_in_api=True)
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
        job_name=f"{job.job_spec.job_name}",
        replica_num=job.job_spec.replica_num,
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
    # FIXME: not safe to share session between tasks – sqlalchemy can error
    await asyncio.gather(*(stop_run(session, run, abort) for run in runs))


async def stop_run(session: AsyncSession, run: RunModel, abort: bool):
    await wait_to_lock(PROCESSING_RUNS_LOCK, PROCESSING_RUNS_IDS, run.id)

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
        logger.debug("%s: terminating because %s", fmt(run), run.termination_reason.name)
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
    active_runs = [r for r in run_models if not r.status.is_finished()]
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
            f"Backends {backends} do not support create_instance. Try to select other backends."
        )

    if not offers:
        raise ServerClientError(
            "Failed to find offers to create the instance."
        )  # TODO(sergeyme): ComputeError?

    pool = await pools_services.get_or_create_pool_by_name(session, project, profile.pool_name)
    instance_name = await generate_instance_name(
        session=session, project=project, pool_name=pool.name
    )

    termination_policy = profile.termination_policy or TerminationPolicy.DESTROY_AFTER_IDLE
    termination_idle_time = profile.termination_idle_time
    if termination_idle_time is None:
        termination_idle_time = DEFAULT_POOL_TERMINATION_IDLE_TIME

    instance = InstanceModel(
        id=uuid.uuid4(),
        name=instance_name,
        project=project,
        pool=pool,
        created_at=common_utils.get_current_datetime(),
        status=InstanceStatus.PENDING,
        unreachable=False,
        profile=profile.json(),
        requirements=requirements.json(),
        instance_configuration=None,
        termination_policy=termination_policy,
        termination_idle_time=termination_idle_time,
    )
    logger.info(
        "Added a new instance %s",
        instance.name,
        extra={
            "instance_name": instance.name,
            "instance_status": InstanceStatus.PENDING.value,
        },
    )
    session.add(instance)
    await session.commit()

    project_ssh_key = SSHKey(
        public=project.ssh_public_key.strip(),
        private=project.ssh_private_key.strip(),
    )
    dstack_default_image = parse_image_name(get_default_image(get_default_python_verison()))
    instance_config = InstanceConfiguration(
        project_name=project.name,
        instance_name=instance_name,
        instance_id=str(instance.id),
        ssh_keys=[project_ssh_key],
        job_docker_config=DockerConfig(
            image=dstack_default_image,
            registry_auth=None,
        ),
        user=user.name,
    )
    instance.instance_configuration = instance_config.json()
    await session.commit()

    return instance_model_to_instance(instance)


def run_model_to_run(
    run_model: RunModel, include_job_submissions: bool = True, return_in_api: bool = False
) -> Run:
    jobs: List[Job] = []
    run_jobs = sorted(run_model.jobs, key=lambda j: (j.replica_num, j.job_num, j.submission_num))
    for replica_num, replica_submissions in itertools.groupby(
        run_jobs, key=lambda j: j.replica_num
    ):
        for job_num, job_submissions in itertools.groupby(
            replica_submissions, key=lambda j: j.job_num
        ):
            job_spec = None
            submissions = []
            for job_model in job_submissions:
                if job_spec is None:
                    job_spec = JobSpec.__response__.parse_raw(job_model.job_spec_data)
                if include_job_submissions:
                    job_submission = job_model_to_job_submission(job_model)
                    if return_in_api:
                        # Set default non-None values for 0.18 backward-compatibility
                        # Remove in 0.19
                        if job_submission.job_provisioning_data is not None:
                            if job_submission.job_provisioning_data.hostname is None:
                                job_submission.job_provisioning_data.hostname = ""
                            if job_submission.job_provisioning_data.ssh_port is None:
                                job_submission.job_provisioning_data.ssh_port = 22
                    submissions.append(job_submission)
            if job_spec is not None:
                jobs.append(Job(job_spec=job_spec, job_submissions=submissions))

    run_spec = RunSpec.__response__.parse_raw(run_model.run_spec)

    latest_job_submission = None
    if include_job_submissions:
        # TODO(egor-s): does it make sense with replicas and multi-node?
        if jobs:
            latest_job_submission = jobs[0].job_submissions[-1]

    service_spec = None
    if run_model.service_spec is not None:
        service_spec = ServiceSpec.__response__.parse_raw(run_model.service_spec)

    run = Run(
        id=run_model.id,
        project_name=run_model.project.name,
        user=run_model.user.name,
        submitted_at=run_model.submitted_at.replace(tzinfo=timezone.utc),
        last_processed_at=run_model.last_processed_at.replace(tzinfo=timezone.utc),
        status=run_model.status,
        termination_reason=run_model.termination_reason,
        run_spec=run_spec,
        jobs=jobs,
        latest_job_submission=latest_job_submission,
        service=service_spec,
    )
    run.cost = _get_run_cost(run)
    return run


_PROJECTS_TO_RUN_NAMES_LOCK = {}


def _get_pool_offers(
    pool: PoolModel,
    run_spec: RunSpec,
    job: Job,
    volumes: List[Volume],
) -> List[InstanceOfferWithAvailability]:
    profile = run_spec.merged_profile
    requirements = Requirements(
        resources=run_spec.configuration.resources,
        max_price=profile.max_price,
        spot=get_policy_map(profile.spot_policy, default=SpotPolicy.AUTO),
    )
    pool_filtered_instances = filter_pool_instances(
        pool_instances=get_pool_instances(pool),
        profile=profile,
        requirements=requirements,
        multinode=job.job_spec.jobs_per_replica > 1,
        volumes=volumes,
    )
    pool_offers: List[InstanceOfferWithAvailability] = []
    for instance in pool_filtered_instances:
        offer = get_instance_offer(instance)
        if offer is None:
            continue
        offer.availability = InstanceAvailability.BUSY
        if instance.status == InstanceStatus.IDLE:
            offer.availability = InstanceAvailability.IDLE
        if instance.unreachable:
            offer.availability = InstanceAvailability.NOT_AVAILABLE
        pool_offers.append(offer)
    return pool_offers


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


async def validate_run(
    session: AsyncSession,
    user: UserModel,
    project: ProjectModel,
    run_spec: RunSpec,
):
    volumes = await get_run_volumes(
        session=session,
        project=project,
        run_spec=run_spec,
    )
    check_can_attach_run_volumes(
        run_spec=run_spec,
        volumes=volumes,
    )


async def get_run_volumes(
    session: AsyncSession,
    project: ProjectModel,
    run_spec: RunSpec,
) -> List[Volume]:
    volume_models = await get_run_volume_models(
        session=session,
        project=project,
        run_spec=run_spec,
    )
    return [volumes_services.volume_model_to_volume(v) for v in volume_models]


async def get_run_volume_models(
    session: AsyncSession,
    project: ProjectModel,
    run_spec: RunSpec,
) -> List[VolumeModel]:
    if len(run_spec.configuration.volumes) == 0:
        return []
    volume_models = []
    for mount_point in run_spec.configuration.volumes:
        volume_model = await volumes_services.get_project_volume_model_by_name(
            session=session,
            project=project,
            name=mount_point.name,
        )
        if volume_model is None:
            raise ResourceNotExistsError(f"Volume {mount_point.name} not found")
        volume_models.append(volume_model)
    return volume_models


def check_can_attach_run_volumes(
    run_spec: RunSpec,
    volumes: List[Volume],
):
    if len(volumes) == 0:
        return
    # Perform basic checks if volumes can be attached.
    # This is useful to show error ASAP (when user submits the run).
    # If the attachment is to fail anyway, the error will be handled when proccessing submitted jobs.
    backend = volumes[0].configuration.backend
    region = volumes[0].configuration.region
    for volume in volumes:
        if backend != volume.configuration.backend:
            raise ServerClientError("Cannot mount volumes from different backends")
        if region != volume.configuration.region:
            raise ServerClientError("Cannot mount volumes from different regions")
        if volume.status != VolumeStatus.ACTIVE:
            raise ServerClientError("Cannot mount volumes that are not active")


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


def _validate_run_spec(run_spec: RunSpec):
    if run_spec.run_name is not None:
        validate_dstack_resource_name(run_spec.run_name)
    for mount_point in run_spec.configuration.volumes:
        if not is_valid_docker_volume_target(mount_point.path):
            raise ServerClientError(f"Invalid volume mount path: {mount_point.path}")
        if mount_point.path.startswith("/workflow"):
            raise ServerClientError("Mounting volumes inside /workflow is not supported")


async def process_terminating_run(session: AsyncSession, run: RunModel):
    """
    Used by both `process_runs` and `stop_run` to process a run that is TERMINATING.
    Caller must acquire the lock on run.
    """

    assert run.termination_reason is not None
    job_termination_reason = run.termination_reason.to_job_termination_reason()

    jobs_ids_set = {job.id for job in run.jobs}
    await wait_unlock(RUNNING_PROCESSING_JOBS_LOCK, RUNNING_PROCESSING_JOBS_IDS, jobs_ids_set)
    await wait_unlock(SUBMITTED_PROCESSING_JOBS_LOCK, SUBMITTED_PROCESSING_JOBS_IDS, jobs_ids_set)
    await wait_unlock(
        TERMINATING_PROCESSING_JOBS_LOCK, TERMINATING_PROCESSING_JOBS_IDS, jobs_ids_set
    )
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
        if run.gateway_id is not None:
            try:
                await gateways.unregister_service(session, run)
            except Exception as e:
                logger.warning("%s: failed to unregister service: %s", fmt(run), repr(e))
        run.status = run.termination_reason.to_status()
        logger.info(
            "%s: run status has changed TERMINATING -> %s, reason: %s",
            fmt(run),
            run.status.name,
            run.termination_reason.name,
        )


async def scale_run_replicas(session: AsyncSession, run_model: RunModel, replicas_diff: int):
    if replicas_diff == 0:
        # nothing to do
        return

    logger.info(
        "%s: scaling %s %s replica(s)",
        fmt(run_model),
        "UP" if replicas_diff > 0 else "DOWN",
        abs(replicas_diff),
    )

    # lists of (importance, replica_num, jobs)
    active_replicas = []
    inactive_replicas = []

    for replica_num, replica_jobs in group_jobs_by_replica_latest(run_model.jobs):
        statuses = set(job.status for job in replica_jobs)
        if {JobStatus.TERMINATING, *JobStatus.finished_statuses()} & statuses:
            # if there are any terminating or finished jobs, the replica is inactive
            inactive_replicas.append((0, replica_num, replica_jobs))
        elif JobStatus.SUBMITTED in statuses:
            # if there are any submitted jobs, the replica is active and has the importance of 0
            active_replicas.append((0, replica_num, replica_jobs))
        elif {JobStatus.PROVISIONING, JobStatus.PULLING} & statuses:
            # if there are any provisioning or pulling jobs, the replica is active and has the importance of 1
            active_replicas.append((1, replica_num, replica_jobs))
        else:
            # all jobs are running, the replica is active and has the importance of 2
            active_replicas.append((2, replica_num, replica_jobs))

    # sort by importance (desc) and replica_num (asc)
    active_replicas.sort(key=lambda r: (-r[0], r[1]))
    run_spec = RunSpec.__response__.parse_raw(run_model.run_spec)

    if replicas_diff < 0:
        if len(active_replicas) + replicas_diff < run_spec.configuration.replicas.min:
            raise ServerClientError("Can't scale down below the minimum number of replicas")

        for _, _, replica_jobs in reversed(active_replicas[-abs(replicas_diff) :]):
            # scale down the less important replicas first
            for job in replica_jobs:
                if job.status.is_finished() or job.status == JobStatus.TERMINATING:
                    continue
                job.status = JobStatus.TERMINATING
                job.termination_reason = JobTerminationReason.SCALED_DOWN
                # background task will process the job later
    else:
        if len(active_replicas) + replicas_diff > run_spec.configuration.replicas.max:
            raise ServerClientError("Can't scale up above the maximum number of replicas")
        scheduled_replicas = 0

        # rerun inactive replicas
        for _, _, replica_jobs in inactive_replicas:
            if scheduled_replicas == replicas_diff:
                break
            await retry_run_replica_jobs(session, run_model, replica_jobs, only_failed=False)
            scheduled_replicas += 1

        # create new replicas
        for replica_num in range(
            len(active_replicas) + scheduled_replicas, len(active_replicas) + replicas_diff
        ):
            jobs = await get_jobs_from_run_spec(run_spec, replica_num=replica_num)
            for job in jobs:
                job_model = create_job_model_for_new_submission(
                    run_model=run_model,
                    job=job,
                    status=JobStatus.SUBMITTED,
                )
                session.add(job_model)


async def retry_run_replica_jobs(
    session: AsyncSession, run_model: RunModel, latest_jobs: List[JobModel], *, only_failed: bool
):
    for job_model in latest_jobs:
        if not (job_model.status.is_finished() or job_model.status == JobStatus.TERMINATING):
            if only_failed:
                # No need to resubmit, skip
                continue
            # The job is not finished, but we have to retry all jobs. Terminate it
            job_model.status = JobStatus.TERMINATING
            job_model.termination_reason = JobTerminationReason.TERMINATED_BY_SERVER

        new_job_model = create_job_model_for_new_submission(
            run_model=run_model,
            job=Job(
                job_spec=JobSpec.__response__.parse_raw(job_model.job_spec_data),
                job_submissions=[],
            ),
            status=JobStatus.SUBMITTED,
        )
        # dirty hack to avoid passing all job submissions
        new_job_model.submission_num = job_model.submission_num + 1
        session.add(new_job_model)
