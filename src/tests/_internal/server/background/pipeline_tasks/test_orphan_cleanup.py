import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.backends.base.compute import ComputeWithResourceListingSupport
from dstack._internal.core.errors import BackendError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.backends.orphans import (
    ListedResourceGroup,
    OrphanCleanupMode,
    OwnerType,
    ResourceListing,
    ResourceListingFailure,
)
from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.core.models.runs import JobStatus
from dstack._internal.server import settings
from dstack._internal.server.background.pipeline_tasks import (
    orphan_cleanup as orphan_cleanup_pipeline,
)
from dstack._internal.server.background.pipeline_tasks.base import PipelineItem
from dstack._internal.server.background.pipeline_tasks.orphan_cleanup import (
    OrphanCleanupFetcher,
    OrphanCleanupPipeline,
    OrphanCleanupWorker,
    _get_resource_group_decision,
    _OwnerRecords,
    _ResourceGroupDecision,
)
from dstack._internal.server.models import (
    BackendModel,
    InstanceModel,
    JobModel,
    OrphanCleanupModel,
    ProjectModel,
)
from dstack._internal.server.testing.common import (
    create_backend,
    create_instance,
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_job_provisioning_data,
    list_events,
)
from dstack._internal.utils.common import get_current_datetime

LISTED_AT = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
PROVIDER_REF = "abc123def456"


def _get_orphan_cleanup_model() -> OrphanCleanupModel:
    return OrphanCleanupModel(
        backend=BackendModel(type=BackendType.AWS, project=ProjectModel(name="test-project"))
    )


def _get_resource_group(
    primary_id: Optional[str] = "instance_id",
    backend: BackendType = BackendType.AWS,
    created_at: datetime = LISTED_AT - timedelta(minutes=5),
) -> ListedResourceGroup:
    return ListedResourceGroup(
        backend=backend,
        owner_type=OwnerType.INSTANCE,
        provider_ref=PROVIDER_REF,
        primary_id=primary_id,
        region="us-east-1",
        created_at=created_at,
        description="VM",
        backend_data=None,
    )


def _get_instance_model(status: InstanceStatus, provisioned: bool = True) -> InstanceModel:
    job_provisioning_data = None
    if provisioned:
        # `instance_id` is "instance_id"
        job_provisioning_data = get_job_provisioning_data(backend=BackendType.AWS)
    return InstanceModel(
        name="test-instance",
        status=status,
        provider_ref=PROVIDER_REF,
        job_provisioning_data=(
            job_provisioning_data.model_dump_json() if job_provisioning_data else None
        ),
    )


def _get_job_model(status: JobStatus) -> JobModel:
    return JobModel(job_name="test-job", status=status, provider_ref=PROVIDER_REF)


def _get_decision(
    resource_group: ListedResourceGroup,
    instance_model: Optional[InstanceModel] = None,
    job_model: Optional[JobModel] = None,
) -> _ResourceGroupDecision:
    owner_records = _OwnerRecords(
        instances={PROVIDER_REF: instance_model} if instance_model is not None else {},
        jobs={PROVIDER_REF: job_model} if job_model is not None else {},
    )
    return _get_resource_group_decision(
        _get_orphan_cleanup_model(), resource_group, owner_records, LISTED_AT
    )


class TestGetResourceGroupDecision:
    def test_ignores_group_without_owner_record(self):
        assert _get_decision(_get_resource_group()) == _ResourceGroupDecision.IGNORE

    @pytest.mark.parametrize("status", [InstanceStatus.PENDING, InstanceStatus.TERMINATING])
    def test_skips_group_of_transitional_instance(self, status: InstanceStatus):
        instance_model = _get_instance_model(status, provisioned=False)
        decision = _get_decision(_get_resource_group(), instance_model=instance_model)
        assert decision == _ResourceGroupDecision.SKIP

    def test_skips_old_group_of_pending_instance(self):
        instance_model = _get_instance_model(InstanceStatus.PENDING, provisioned=False)
        resource_group = _get_resource_group(created_at=LISTED_AT - timedelta(hours=2))
        decision = _get_decision(resource_group, instance_model=instance_model)
        assert decision == _ResourceGroupDecision.SKIP

    @pytest.mark.parametrize("provisioned", [True, False])
    def test_orphans_group_of_terminated_instance(self, provisioned: bool):
        instance_model = _get_instance_model(InstanceStatus.TERMINATED, provisioned=provisioned)
        decision = _get_decision(_get_resource_group(), instance_model=instance_model)
        assert decision == _ResourceGroupDecision.ORPHAN

    def test_tracks_group_matching_active_instance(self):
        instance_model = _get_instance_model(InstanceStatus.BUSY)
        decision = _get_decision(_get_resource_group(), instance_model=instance_model)
        assert decision == _ResourceGroupDecision.TRACKED

    def test_orphans_group_with_other_primary_id_of_active_instance(self):
        instance_model = _get_instance_model(InstanceStatus.BUSY)
        resource_group = _get_resource_group(primary_id="other_instance_id")
        decision = _get_decision(resource_group, instance_model=instance_model)
        assert decision == _ResourceGroupDecision.ORPHAN

    def test_orphans_group_without_primary_resource_of_active_instance(self):
        instance_model = _get_instance_model(InstanceStatus.BUSY)
        resource_group = _get_resource_group(primary_id=None)
        decision = _get_decision(resource_group, instance_model=instance_model)
        assert decision == _ResourceGroupDecision.ORPHAN

    def test_orphans_group_in_other_backend_of_active_instance(self):
        instance_model = _get_instance_model(InstanceStatus.BUSY)
        resource_group = _get_resource_group(backend=BackendType.GCP)
        decision = _get_decision(resource_group, instance_model=instance_model)
        assert decision == _ResourceGroupDecision.ORPHAN

    def test_ignores_active_instance_without_provisioning_data(self):
        instance_model = _get_instance_model(InstanceStatus.BUSY, provisioned=False)
        decision = _get_decision(_get_resource_group(), instance_model=instance_model)
        assert decision == _ResourceGroupDecision.IGNORE

    def test_skips_group_of_submitted_job_without_instance(self):
        job_model = _get_job_model(JobStatus.SUBMITTED)
        decision = _get_decision(_get_resource_group(), job_model=job_model)
        assert decision == _ResourceGroupDecision.SKIP

    @pytest.mark.parametrize(
        "status", [JobStatus.RUNNING, JobStatus.TERMINATING, JobStatus.FAILED]
    )
    def test_orphans_group_of_not_submitted_job_without_instance(self, status: JobStatus):
        job_model = _get_job_model(status)
        decision = _get_decision(_get_resource_group(), job_model=job_model)
        assert decision == _ResourceGroupDecision.ORPHAN

    def test_prefers_instance_over_job(self):
        instance_model = _get_instance_model(InstanceStatus.BUSY)
        job_model = _get_job_model(JobStatus.RUNNING)
        decision = _get_decision(
            _get_resource_group(), instance_model=instance_model, job_model=job_model
        )
        assert decision == _ResourceGroupDecision.TRACKED


CLEANUP_INTERVAL = timedelta(seconds=settings.ORPHAN_CLEANUP_INTERVAL_SECONDS)


class _ListingCompute(ComputeWithResourceListingSupport):
    def __init__(
        self,
        listing: Optional[ResourceListing] = None,
        error: Optional[Exception] = None,
    ):
        self.listing = listing or ResourceListing(resource_groups=[])
        self.error = error
        self.listed = False
        self.deleted: list[ListedResourceGroup] = []

    def list_resource_groups(self) -> ResourceListing:
        self.listed = True
        if self.error is not None:
            raise self.error
        return self.listing

    def delete_resource_group(self, group: ListedResourceGroup) -> None:
        self.deleted.append(group)


async def _create_orphan_cleanup(
    session: AsyncSession,
    project: ProjectModel,
    *,
    last_processed_at: datetime,
    created_at: Optional[datetime] = None,
    clean_at: Optional[datetime] = None,
    clean_mode: Optional[OrphanCleanupMode] = None,
    cleanup_attempt: int = 0,
    backend_type: BackendType = BackendType.AWS,
) -> OrphanCleanupModel:
    backend = await create_backend(
        session=session, project_id=project.id, backend_type=backend_type
    )
    orphan_cleanup = OrphanCleanupModel(
        backend_id=backend.id,
        created_at=created_at or last_processed_at - timedelta(days=1),
        last_processed_at=last_processed_at,
        clean_at=clean_at,
        clean_mode=clean_mode,
        cleanup_attempt=cleanup_attempt,
    )
    session.add(orphan_cleanup)
    await session.commit()
    return orphan_cleanup


async def _create_instance_with_provider_ref(
    session: AsyncSession,
    project: ProjectModel,
    status: InstanceStatus,
    created_at: datetime = LISTED_AT,
) -> InstanceModel:
    instance = await create_instance(
        session=session, project=project, status=status, created_at=created_at
    )
    instance.provider_ref = PROVIDER_REF
    await session.commit()
    return instance


async def _fetch_ids(fetcher: OrphanCleanupFetcher) -> set[uuid.UUID]:
    return {item.id for item in await fetcher.fetch(limit=10)}


@pytest.fixture
def fetcher() -> OrphanCleanupFetcher:
    return OrphanCleanupFetcher(
        queue=asyncio.Queue(),
        queue_desired_minsize=1,
        min_processing_interval=CLEANUP_INTERVAL,
        lock_timeout=timedelta(seconds=60),
        heartbeater=Mock(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestOrphanCleanupFetcher:
    async def test_fetches_new_rows(self, test_db, session: AsyncSession, fetcher):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        now = get_current_datetime()
        orphan_cleanup = await _create_orphan_cleanup(
            session, project, last_processed_at=now, created_at=now
        )
        assert await _fetch_ids(fetcher) == {orphan_cleanup.id}

    async def test_fetches_clean_rows_after_cleanup_interval(
        self, test_db, session: AsyncSession, fetcher
    ):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        clean_at = get_current_datetime() - 2 * CLEANUP_INTERVAL
        orphan_cleanup = await _create_orphan_cleanup(
            session,
            project,
            last_processed_at=clean_at,
            clean_at=clean_at,
            clean_mode=settings.ORPHAN_CLEANUP_MODE,
        )
        assert await _fetch_ids(fetcher) == {orphan_cleanup.id}

    async def test_skips_rows_processed_within_cleanup_interval(
        self, test_db, session: AsyncSession, fetcher
    ):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        await _create_orphan_cleanup(
            session, project, last_processed_at=get_current_datetime() - CLEANUP_INTERVAL / 2
        )
        assert await _fetch_ids(fetcher) == set()

    async def test_skips_rows_of_deleted_projects_and_unsupported_backends(
        self, test_db, session: AsyncSession, fetcher
    ):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        now = get_current_datetime()
        deleted_project = await create_project(
            session=session, owner=user, name="deleted-project", deleted=True
        )
        await _create_orphan_cleanup(
            session, deleted_project, last_processed_at=now, created_at=now
        )
        await _create_orphan_cleanup(
            session,
            project,
            last_processed_at=now,
            created_at=now,
            backend_type=BackendType.LAMBDA,
        )
        assert await _fetch_ids(fetcher) == set()

    @pytest.mark.parametrize(
        ("cleanup_attempt", "intervals_since_processed", "fetched"),
        [
            (1, 1.5, False),
            (1, 2.5, True),
            (5, 23, False),
            (5, 25, True),
        ],
    )
    async def test_applies_retry_delay_after_failed_cleanups(
        self,
        test_db,
        session: AsyncSession,
        fetcher,
        cleanup_attempt: int,
        intervals_since_processed: float,
        fetched: bool,
    ):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        orphan_cleanup = await _create_orphan_cleanup(
            session,
            project,
            last_processed_at=get_current_datetime()
            - CLEANUP_INTERVAL * intervals_since_processed,
            cleanup_attempt=cleanup_attempt,
        )
        assert await _fetch_ids(fetcher) == ({orphan_cleanup.id} if fetched else set())


async def _lock(session: AsyncSession, orphan_cleanup: OrphanCleanupModel) -> PipelineItem:
    lock_token = uuid.uuid4()
    lock_expires_at = get_current_datetime() + timedelta(seconds=60)
    orphan_cleanup.lock_token = lock_token
    orphan_cleanup.lock_expires_at = lock_expires_at
    orphan_cleanup.lock_owner = OrphanCleanupPipeline.__name__
    await session.commit()
    return PipelineItem(
        __tablename__=OrphanCleanupModel.__tablename__,
        id=orphan_cleanup.id,
        lock_token=lock_token,
        lock_expires_at=lock_expires_at,
        prev_lock_expired=False,
    )


def _patch_compute(compute: _ListingCompute):
    backend = Mock()
    backend.compute.return_value = compute
    return patch.object(
        orphan_cleanup_pipeline.backends_services,
        "get_project_backend_by_type",
        AsyncMock(return_value=backend),
    )


@pytest.fixture
def worker() -> OrphanCleanupWorker:
    return OrphanCleanupWorker(queue=Mock(), heartbeater=Mock(), pipeline_hinter=Mock())


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestOrphanCleanupWorker:
    async def test_reports_orphans_and_marks_backend_clean(
        self, test_db, session: AsyncSession, worker
    ):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        orphan_cleanup = await _create_orphan_cleanup(
            session, project, last_processed_at=get_current_datetime(), cleanup_attempt=2
        )
        await _create_instance_with_provider_ref(session, project, InstanceStatus.TERMINATED)
        compute = _ListingCompute(ResourceListing(resource_groups=[_get_resource_group()]))
        item = await _lock(session, orphan_cleanup)
        with (
            patch.object(settings, "ORPHAN_CLEANUP_MODE", OrphanCleanupMode.REPORT),
            _patch_compute(compute),
        ):
            await worker.process(item)
        await session.refresh(orphan_cleanup)
        assert orphan_cleanup.clean_at is not None
        assert orphan_cleanup.clean_mode == OrphanCleanupMode.REPORT
        assert orphan_cleanup.cleanup_attempt == 0
        assert orphan_cleanup.lock_token is None
        assert compute.deleted == []
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message.startswith("Orphaned resources found in aws/us-east-1")

    @pytest.mark.parametrize(
        "activity", ["instance_created", "instance_started", "instance_finished", "job_finished"]
    )
    async def test_cleans_up_backend_with_activity_after_clean_at(
        self, test_db, session: AsyncSession, worker, activity: str
    ):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        clean_at = get_current_datetime() - 2 * CLEANUP_INTERVAL
        before_clean_at = clean_at - timedelta(minutes=10)
        after_clean_at = clean_at + timedelta(minutes=10)
        orphan_cleanup = await _create_orphan_cleanup(
            session,
            project,
            last_processed_at=clean_at,
            clean_at=clean_at,
            clean_mode=settings.ORPHAN_CLEANUP_MODE,
        )
        if activity == "job_finished":
            repo = await create_repo(session=session, project_id=project.id)
            run = await create_run(session=session, project=project, repo=repo, user=user)
            await create_job(
                session=session,
                run=run,
                status=JobStatus.FAILED,
                last_processed_at=after_clean_at,
                provider_ref=PROVIDER_REF,
            )
        else:
            instance = await _create_instance_with_provider_ref(
                session,
                project,
                InstanceStatus.TERMINATED,
                created_at=after_clean_at if activity == "instance_created" else before_clean_at,
            )
            if activity == "instance_started":
                instance.started_at = after_clean_at
            if activity == "instance_finished":
                instance.finished_at = after_clean_at
            await session.commit()
        compute = _ListingCompute()
        item = await _lock(session, orphan_cleanup)
        with _patch_compute(compute):
            await worker.process(item)
        await session.refresh(orphan_cleanup)
        assert compute.listed
        assert orphan_cleanup.clean_at is not None
        assert orphan_cleanup.clean_at > clean_at

    async def test_skips_listing_without_activity_after_clean_at(
        self, test_db, session: AsyncSession, worker
    ):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        clean_at = get_current_datetime() - 2 * CLEANUP_INTERVAL
        orphan_cleanup = await _create_orphan_cleanup(
            session,
            project,
            last_processed_at=clean_at,
            clean_at=clean_at,
            clean_mode=settings.ORPHAN_CLEANUP_MODE,
        )
        await _create_instance_with_provider_ref(
            session,
            project,
            InstanceStatus.IDLE,
            created_at=clean_at - timedelta(minutes=10),
        )
        compute = _ListingCompute()
        item = await _lock(session, orphan_cleanup)
        with _patch_compute(compute):
            await worker.process(item)
        await session.refresh(orphan_cleanup)
        assert not compute.listed
        assert orphan_cleanup.clean_at == clean_at
        assert orphan_cleanup.last_processed_at > clean_at
        assert orphan_cleanup.lock_token is None

    async def test_cleans_up_backend_cleaned_in_other_mode(
        self, test_db, session: AsyncSession, worker
    ):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        clean_at = get_current_datetime() - 2 * CLEANUP_INTERVAL
        orphan_cleanup = await _create_orphan_cleanup(
            session,
            project,
            last_processed_at=clean_at,
            clean_at=clean_at,
            clean_mode=OrphanCleanupMode.DELETE,
        )
        compute = _ListingCompute()
        item = await _lock(session, orphan_cleanup)
        with (
            patch.object(settings, "ORPHAN_CLEANUP_MODE", OrphanCleanupMode.REPORT),
            _patch_compute(compute),
        ):
            await worker.process(item)
        await session.refresh(orphan_cleanup)
        assert compute.listed
        assert orphan_cleanup.clean_mode == OrphanCleanupMode.REPORT

    async def test_deletes_orphans_in_delete_mode(self, test_db, session: AsyncSession, worker):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        orphan_cleanup = await _create_orphan_cleanup(
            session, project, last_processed_at=get_current_datetime()
        )
        await _create_instance_with_provider_ref(session, project, InstanceStatus.TERMINATED)
        resource_group = _get_resource_group()
        compute = _ListingCompute(ResourceListing(resource_groups=[resource_group]))
        item = await _lock(session, orphan_cleanup)
        with (
            patch.object(settings, "ORPHAN_CLEANUP_MODE", OrphanCleanupMode.DELETE),
            _patch_compute(compute),
        ):
            await worker.process(item)
        await session.refresh(orphan_cleanup)
        assert orphan_cleanup.clean_mode == OrphanCleanupMode.DELETE
        assert compute.deleted == [resource_group]
        events = await list_events(session)
        assert [e.message.split(" in ")[0] for e in events] == ["Orphaned resources deleted"]

    async def test_keeps_backend_due_without_backoff_after_partial_listing(
        self, test_db, session: AsyncSession, worker
    ):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        orphan_cleanup = await _create_orphan_cleanup(
            session, project, last_processed_at=get_current_datetime(), cleanup_attempt=2
        )
        compute = _ListingCompute(
            ResourceListing(
                resource_groups=[],
                failures=[
                    ResourceListingFailure(
                        backend=BackendType.AWS, region="us-east-1", message="throttled"
                    )
                ],
            )
        )
        item = await _lock(session, orphan_cleanup)
        with _patch_compute(compute):
            await worker.process(item)
        await session.refresh(orphan_cleanup)
        assert orphan_cleanup.clean_at is None
        assert orphan_cleanup.cleanup_attempt == 0

    async def test_backs_off_after_listing_error(self, test_db, session: AsyncSession, worker):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        orphan_cleanup = await _create_orphan_cleanup(
            session, project, last_processed_at=get_current_datetime(), cleanup_attempt=1
        )
        compute = _ListingCompute(error=BackendError("unauthorized"))
        item = await _lock(session, orphan_cleanup)
        with _patch_compute(compute):
            await worker.process(item)
        await session.refresh(orphan_cleanup)
        assert orphan_cleanup.clean_at is None
        assert orphan_cleanup.cleanup_attempt == 2

    async def test_backs_off_when_owner_is_in_flight(self, test_db, session: AsyncSession, worker):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        orphan_cleanup = await _create_orphan_cleanup(
            session, project, last_processed_at=get_current_datetime()
        )
        await _create_instance_with_provider_ref(session, project, InstanceStatus.PENDING)
        compute = _ListingCompute(ResourceListing(resource_groups=[_get_resource_group()]))
        item = await _lock(session, orphan_cleanup)
        with _patch_compute(compute):
            await worker.process(item)
        await session.refresh(orphan_cleanup)
        assert orphan_cleanup.clean_at is None
        assert orphan_cleanup.cleanup_attempt == 1
        assert compute.deleted == []

    async def test_does_not_apply_result_if_lock_token_changes(
        self, test_db, session: AsyncSession, worker
    ):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        orphan_cleanup = await _create_orphan_cleanup(
            session, project, last_processed_at=get_current_datetime()
        )
        await _create_instance_with_provider_ref(session, project, InstanceStatus.TERMINATED)
        compute = _ListingCompute(ResourceListing(resource_groups=[_get_resource_group()]))
        item = await _lock(session, orphan_cleanup)
        new_lock_token = uuid.uuid4()
        load_owner_records = orphan_cleanup_pipeline._load_owner_records

        async def load_owner_records_after_lock_takeover(**kwargs):
            # Another worker takes over the row while it's being processed
            orphan_cleanup.lock_token = new_lock_token
            await session.commit()
            return await load_owner_records(**kwargs)

        with (
            _patch_compute(compute),
            patch.object(
                orphan_cleanup_pipeline,
                "_load_owner_records",
                side_effect=load_owner_records_after_lock_takeover,
            ),
        ):
            await worker.process(item)
        await session.refresh(orphan_cleanup)
        assert orphan_cleanup.lock_token == new_lock_token
        assert orphan_cleanup.clean_at is None
        assert await list_events(session) == []
