from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.backends.orphans import ListedResourceGroup, OwnerType
from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.core.models.runs import JobStatus
from dstack._internal.server.background.pipeline_tasks.orphan_cleanup import (
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
from dstack._internal.server.testing.common import get_job_provisioning_data

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
