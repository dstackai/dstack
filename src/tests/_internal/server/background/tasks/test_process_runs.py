import datetime
from collections.abc import Iterable
from typing import Union, cast
from unittest.mock import patch

import pytest
from freezegun import freeze_time
from pydantic import parse_obj_as
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.server.background.tasks.process_runs as process_runs
from dstack._internal.core.models.configurations import (
    ProbeConfig,
    ServiceConfiguration,
    TaskConfiguration,
)
from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.core.models.profiles import Profile, ProfileRetry, Schedule
from dstack._internal.core.models.resources import Range
from dstack._internal.core.models.runs import (
    JobSpec,
    JobStatus,
    JobTerminationReason,
    RunSpec,
    RunStatus,
    RunTerminationReason,
)
from dstack._internal.server.models import RunModel
from dstack._internal.server.testing.common import (
    create_instance,
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_job_provisioning_data,
    get_run_spec,
)
from dstack._internal.utils import common

pytestmark = pytest.mark.usefixtures("image_config_mock")


async def make_run(
    session: AsyncSession,
    status: RunStatus = RunStatus.SUBMITTED,
    replicas: Union[str, int] = 1,
    deployment_num: int = 0,
    image: str = "ubuntu:latest",
    probes: Iterable[ProbeConfig] = (),
) -> RunModel:
    project = await create_project(session=session)
    user = await create_user(session=session)
    repo = await create_repo(
        session=session,
        project_id=project.id,
    )
    run_name = "test-run"
    profile = Profile(
        name="test-profile",
        retry=True,
    )
    run_spec = get_run_spec(
        repo_id=repo.name,
        run_name=run_name,
        profile=profile,
        configuration=ServiceConfiguration(
            commands=["echo hello"],
            port=8000,
            replicas=parse_obj_as(Range[int], replicas),
            image=image,
            probes=list(probes),
        ),
    )
    run = await create_run(
        session=session,
        project=project,
        repo=repo,
        user=user,
        run_name=run_name,
        run_spec=run_spec,
        status=status,
        deployment_num=deployment_num,
    )
    run.project = project
    return run


class TestProcessRuns:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @freeze_time(datetime.datetime(2023, 1, 2, 3, 5, 20, tzinfo=datetime.timezone.utc))
    async def test_submitted_to_provisioning(self, test_db, session: AsyncSession):
        run = await make_run(session, status=RunStatus.SUBMITTED)
        await create_job(session=session, run=run, status=JobStatus.PROVISIONING)
        current_time = common.get_current_datetime()

        expected_duration = (current_time - run.submitted_at).total_seconds()

        with patch(
            "dstack._internal.server.background.tasks.process_runs.run_metrics"
        ) as mock_run_metrics:
            await process_runs.process_runs()

            mock_run_metrics.log_submit_to_provision_duration.assert_called_once()
            args = mock_run_metrics.log_submit_to_provision_duration.call_args[0]
            assert args[1] == run.project.name
            assert args[2] == "service"
            # Assert the duration is close to our expected duration (within 0.05 second tolerance)
            assert args[0] == expected_duration

        await session.refresh(run)
        assert run.status == RunStatus.PROVISIONING

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_provisioning_to_running(self, test_db, session: AsyncSession):
        run = await make_run(session, status=RunStatus.PROVISIONING)
        await create_job(session=session, run=run, status=JobStatus.RUNNING)

        await process_runs.process_runs()
        await session.refresh(run)
        assert run.status == RunStatus.RUNNING

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_keep_provisioning(self, test_db, session: AsyncSession):
        run = await make_run(session, status=RunStatus.PROVISIONING)
        await create_job(session=session, run=run, status=JobStatus.PULLING)

        with patch(
            "dstack._internal.server.background.tasks.process_runs.run_metrics"
        ) as mock_run_metrics:
            await process_runs.process_runs()

            mock_run_metrics.log_submit_to_provision_duration.assert_not_called()
            mock_run_metrics.increment_pending_runs.assert_not_called()

        await session.refresh(run)
        assert run.status == RunStatus.PROVISIONING

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_running_to_done(self, test_db, session: AsyncSession):
        run = await make_run(session, status=RunStatus.RUNNING)
        await create_job(session=session, run=run, status=JobStatus.DONE)

        await process_runs.process_runs()
        await session.refresh(run)
        assert run.status == RunStatus.TERMINATING
        assert run.termination_reason == RunTerminationReason.ALL_JOBS_DONE

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_terminate_run_jobs(self, test_db, session: AsyncSession):
        run = await make_run(session, status=RunStatus.TERMINATING)
        run.termination_reason = RunTerminationReason.JOB_FAILED
        instance = await create_instance(
            session=session,
            project=run.project,
            status=InstanceStatus.BUSY,
        )
        job = await create_job(
            session=session,
            run=run,
            job_provisioning_data=get_job_provisioning_data(),
            status=JobStatus.RUNNING,
            instance=instance,
            instance_assigned=True,
        )

        with patch("dstack._internal.server.services.jobs._stop_runner") as stop_runner:
            await process_runs.process_runs()
            stop_runner.assert_called_once()
        await session.refresh(job)
        assert job.status == JobStatus.TERMINATING
        assert job.termination_reason == JobTerminationReason.TERMINATED_BY_SERVER
        await session.refresh(run)
        assert run.status == RunStatus.TERMINATING

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_retry_running_to_pending(self, test_db, session: AsyncSession):
        run = await make_run(session, status=RunStatus.RUNNING)
        instance = await create_instance(session, project=run.project, spot=True)
        await create_job(
            session=session,
            run=run,
            status=JobStatus.FAILED,
            submitted_at=run.submitted_at,
            last_processed_at=run.submitted_at,
            termination_reason=JobTerminationReason.INTERRUPTED_BY_NO_CAPACITY,
            instance=instance,
            job_provisioning_data=get_job_provisioning_data(),
        )
        with (
            patch("dstack._internal.utils.common.get_current_datetime") as datetime_mock,
            patch(
                "dstack._internal.server.background.tasks.process_runs.run_metrics"
            ) as mock_run_metrics,
        ):
            datetime_mock.return_value = run.submitted_at + datetime.timedelta(minutes=3)
            await process_runs.process_runs()

            mock_run_metrics.increment_pending_runs.assert_called_once_with(
                run.project.name, "service"
            )

        await session.refresh(run)
        assert run.status == RunStatus.PENDING

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_retry_running_to_failed(self, test_db, session: AsyncSession):
        run = await make_run(session, status=RunStatus.RUNNING)
        instance = await create_instance(session, project=run.project, spot=True)
        # job exited with non-zero code
        await create_job(
            session=session,
            run=run,
            status=JobStatus.FAILED,
            termination_reason=None,
            instance=instance,
        )

        with patch("dstack._internal.utils.common.get_current_datetime") as datetime_mock:
            datetime_mock.return_value = run.submitted_at + datetime.timedelta(minutes=3)
            await process_runs.process_runs()
        await session.refresh(run)
        assert run.status == RunStatus.TERMINATING
        assert run.termination_reason == RunTerminationReason.JOB_FAILED

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_pending_to_submitted(self, test_db, session: AsyncSession):
        run = await make_run(session, status=RunStatus.PENDING)
        await create_job(session=session, run=run, status=JobStatus.FAILED)

        await process_runs.process_runs()
        await session.refresh(run)
        assert run.status == RunStatus.SUBMITTED
        assert len(run.jobs) == 2
        assert run.jobs[0].status == JobStatus.FAILED
        assert run.jobs[1].status == JobStatus.SUBMITTED


class TestProcessRunsReplicas:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @freeze_time(datetime.datetime(2023, 1, 2, 3, 5, 20, tzinfo=datetime.timezone.utc))
    async def test_submitted_to_provisioning_if_any(self, test_db, session: AsyncSession):
        run = await make_run(session, status=RunStatus.SUBMITTED, replicas=2)
        await create_job(session=session, run=run, status=JobStatus.SUBMITTED, replica_num=0)
        await create_job(session=session, run=run, status=JobStatus.PROVISIONING, replica_num=1)
        current_time = common.get_current_datetime()

        expected_duration = (current_time - run.submitted_at).total_seconds()

        with patch(
            "dstack._internal.server.background.tasks.process_runs.run_metrics"
        ) as mock_run_metrics:
            await process_runs.process_runs()

            mock_run_metrics.log_submit_to_provision_duration.assert_called_once()
            args = mock_run_metrics.log_submit_to_provision_duration.call_args[0]
            assert args[1] == run.project.name
            assert args[2] == "service"
            assert isinstance(args[0], float)
            assert args[0] == expected_duration

        await session.refresh(run)
        assert run.status == RunStatus.PROVISIONING

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_provisioning_to_running_if_any(self, test_db, session: AsyncSession):
        run = await make_run(session, status=RunStatus.PROVISIONING, replicas=2)
        await create_job(session=session, run=run, status=JobStatus.RUNNING, replica_num=0)
        await create_job(session=session, run=run, status=JobStatus.PROVISIONING, replica_num=1)

        await process_runs.process_runs()
        await session.refresh(run)
        assert run.status == RunStatus.RUNNING

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_all_no_capacity_to_pending(self, test_db, session: AsyncSession):
        run = await make_run(session, status=RunStatus.RUNNING, replicas=2)
        await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            termination_reason=JobTerminationReason.INTERRUPTED_BY_NO_CAPACITY,
            submitted_at=run.submitted_at,
            last_processed_at=run.submitted_at,
            replica_num=0,
            instance=await create_instance(session, project=run.project, spot=True),
            job_provisioning_data=get_job_provisioning_data(),
        )
        await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            termination_reason=JobTerminationReason.INTERRUPTED_BY_NO_CAPACITY,
            submitted_at=run.submitted_at,
            last_processed_at=run.submitted_at,
            replica_num=1,
            instance=await create_instance(session, project=run.project, spot=True),
            job_provisioning_data=get_job_provisioning_data(),
        )
        with (
            patch("dstack._internal.utils.common.get_current_datetime") as datetime_mock,
            patch(
                "dstack._internal.server.background.tasks.process_runs.run_metrics"
            ) as mock_run_metrics,
        ):
            datetime_mock.return_value = run.submitted_at + datetime.timedelta(minutes=3)
            await process_runs.process_runs()

            mock_run_metrics.increment_pending_runs.assert_called_once_with(
                run.project.name, "service"
            )

        await session.refresh(run)
        assert run.status == RunStatus.PENDING

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_some_no_capacity_keep_running(self, test_db, session: AsyncSession):
        run = await make_run(session, status=RunStatus.RUNNING, replicas=2)
        await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            termination_reason=JobTerminationReason.INTERRUPTED_BY_NO_CAPACITY,
            submitted_at=run.submitted_at,
            last_processed_at=run.last_processed_at,
            replica_num=0,
            instance=await create_instance(session, project=run.project, spot=True),
            job_provisioning_data=get_job_provisioning_data(),
        )
        await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            submitted_at=run.submitted_at,
            last_processed_at=run.last_processed_at,
            replica_num=1,
            job_provisioning_data=get_job_provisioning_data(),
        )
        with patch("dstack._internal.utils.common.get_current_datetime") as datetime_mock:
            datetime_mock.return_value = run.submitted_at + datetime.timedelta(minutes=3)
            await process_runs.process_runs()
        await session.refresh(run)
        assert run.status == RunStatus.RUNNING
        assert len(run.jobs) == 3
        assert run.jobs[1].replica_num == 0
        assert run.jobs[1].status == JobStatus.SUBMITTED

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @pytest.mark.parametrize(
        ("job_status", "job_termination_reason"),
        [
            (JobStatus.FAILED, JobTerminationReason.CONTAINER_EXITED_WITH_ERROR),
            (JobStatus.TERMINATING, JobTerminationReason.TERMINATED_BY_SERVER),
            (JobStatus.TERMINATED, JobTerminationReason.TERMINATED_BY_SERVER),
        ],
    )
    async def test_some_failed_to_terminating(
        self,
        test_db,
        session: AsyncSession,
        job_status: JobStatus,
        job_termination_reason: JobTerminationReason,
    ) -> None:
        run = await make_run(session, status=RunStatus.RUNNING, replicas=2)
        await create_job(
            session=session,
            run=run,
            status=job_status,
            termination_reason=job_termination_reason,
            replica_num=0,
        )
        await create_job(session=session, run=run, status=JobStatus.RUNNING, replica_num=1)

        await process_runs.process_runs()
        await session.refresh(run)
        assert run.status == RunStatus.TERMINATING
        assert run.termination_reason == RunTerminationReason.JOB_FAILED

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_pending_to_submitted_adds_replicas(self, test_db, session: AsyncSession):
        run = await make_run(session, status=RunStatus.PENDING, replicas=2)
        await create_job(
            session=session,
            run=run,
            status=JobStatus.FAILED,
            termination_reason=JobTerminationReason.INTERRUPTED_BY_NO_CAPACITY,
            replica_num=0,
        )

        await process_runs.process_runs()
        await session.refresh(run)
        assert run.status == RunStatus.SUBMITTED
        assert len(run.jobs) == 3
        assert run.jobs[1].status == JobStatus.SUBMITTED
        assert run.jobs[1].replica_num == 0
        assert run.jobs[2].status == JobStatus.SUBMITTED
        assert run.jobs[2].replica_num == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_submits_scheduled_run(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        run_name = "test_run"
        run_spec = get_run_spec(
            repo_id=repo.name,
            run_name=run_name,
            configuration=TaskConfiguration(
                nodes=1,
                schedule=Schedule(cron="15 * * * *"),  # can be anything
                commands=["echo Hi!"],
            ),
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name=run_name,
            run_spec=run_spec,
            status=RunStatus.PENDING,
            next_triggered_at=datetime.datetime(2023, 1, 2, 3, 15, tzinfo=datetime.timezone.utc),
        )
        with freeze_time(datetime.datetime(2023, 1, 2, 3, 10, tzinfo=datetime.timezone.utc)):
            # Too early to schedule
            await process_runs.process_runs()
        await session.refresh(run)
        assert run.status == RunStatus.PENDING
        with freeze_time(datetime.datetime(2023, 1, 2, 3, 16, tzinfo=datetime.timezone.utc)):
            # It's time to schedule
            await process_runs.process_runs()
        await session.refresh(run)
        assert run.status == RunStatus.SUBMITTED
        assert len(run.jobs) == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_retries_scheduled_run(self, test_db, session: AsyncSession):
        """
        Scheduled run must be retried according to `retry` even if it's too early to schedule.
        """
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        run_name = "test_run"
        run_spec = get_run_spec(
            repo_id=repo.name,
            run_name=run_name,
            configuration=TaskConfiguration(
                nodes=1,
                schedule=Schedule(cron="15 * * * *"),
                retry=ProfileRetry(duration="1h"),
                commands=["echo Hi!"],
            ),
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name=run_name,
            run_spec=run_spec,
            status=RunStatus.PENDING,
            resubmission_attempt=1,
            next_triggered_at=datetime.datetime(2023, 1, 2, 3, 15, tzinfo=datetime.timezone.utc),
        )
        await create_job(
            session=session,
            run=run,
            status=JobStatus.FAILED,
            last_processed_at=datetime.datetime(2023, 1, 2, 3, 0, tzinfo=datetime.timezone.utc),
        )
        with freeze_time(datetime.datetime(2023, 1, 2, 3, 10, tzinfo=datetime.timezone.utc)):
            # Too early to schedule but ready to retry
            await process_runs.process_runs()
        await session.refresh(run)
        assert run.status == RunStatus.SUBMITTED
        assert len(run.jobs) == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_schedules_terminating_run(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        run_name = "test_run"
        run_spec = get_run_spec(
            repo_id=repo.name,
            run_name=run_name,
            configuration=TaskConfiguration(
                nodes=1,
                schedule=Schedule(cron="15 * * * *"),
                commands=["echo Hi!"],
            ),
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name=run_name,
            run_spec=run_spec,
            status=RunStatus.TERMINATING,
            termination_reason=RunTerminationReason.ALL_JOBS_DONE,
            resubmission_attempt=1,
        )
        with freeze_time(datetime.datetime(2023, 1, 2, 3, 10, tzinfo=datetime.timezone.utc)):
            # Too early to schedule but ready to retry
            await process_runs.process_runs()
        await session.refresh(run)
        assert run.status == RunStatus.PENDING
        assert run.next_triggered_at is not None
        assert run.next_triggered_at == datetime.datetime(
            2023, 1, 2, 3, 15, tzinfo=datetime.timezone.utc
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestRollingDeployment:
    @pytest.mark.parametrize(
        ("run_status", "job_statuses"),
        [
            (RunStatus.RUNNING, (JobStatus.RUNNING, JobStatus.RUNNING)),
            (RunStatus.RUNNING, (JobStatus.RUNNING, JobStatus.PULLING)),
            (RunStatus.PROVISIONING, (JobStatus.PROVISIONING, JobStatus.PULLING)),
            (RunStatus.PROVISIONING, (JobStatus.PROVISIONING, JobStatus.PROVISIONING)),
        ],
    )
    async def test_updates_deployment_num_in_place(
        self,
        test_db,
        session: AsyncSession,
        run_status: RunStatus,
        job_statuses: tuple[JobStatus, JobStatus],
    ) -> None:
        run = await make_run(session, status=run_status, replicas=2, deployment_num=1)
        for replica_num, job_status in enumerate(job_statuses):
            await create_job(
                session=session,
                run=run,
                status=job_status,
                replica_num=replica_num,
                deployment_num=0,  # out of date
            )

        await process_runs.process_runs()
        await session.refresh(run)
        assert run.status == run_status
        assert len(run.jobs) == 2
        assert run.jobs[0].status == job_statuses[0]
        assert run.jobs[0].replica_num == 0
        assert run.jobs[0].deployment_num == 1  # updated
        assert run.jobs[1].status == job_statuses[1]
        assert run.jobs[1].replica_num == 1
        assert run.jobs[1].deployment_num == 1  # updated

    async def test_not_updates_deployment_num_in_place_for_finished_replica(
        self, test_db, session: AsyncSession
    ) -> None:
        run = await make_run(session, status=RunStatus.RUNNING, deployment_num=1)
        await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            replica_num=0,
            deployment_num=0,  # out of date
        )
        await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATED,
            termination_reason=JobTerminationReason.SCALED_DOWN,
            replica_num=1,
            deployment_num=0,  # out of date
        )

        await process_runs.process_runs()
        await session.refresh(run)
        assert run.status == RunStatus.RUNNING
        assert len(run.jobs) == 2
        assert run.jobs[0].status == JobStatus.RUNNING
        assert run.jobs[0].replica_num == 0
        assert run.jobs[0].deployment_num == 1  # updated
        assert run.jobs[1].status == JobStatus.TERMINATED
        assert run.jobs[1].replica_num == 1
        assert run.jobs[1].deployment_num == 0  # not updated

    async def test_starts_new_replica(self, test_db, session: AsyncSession) -> None:
        run = await make_run(session, status=RunStatus.RUNNING, replicas=2, image="old")
        for replica_num in range(2):
            await create_job(
                session=session,
                run=run,
                status=JobStatus.RUNNING,
                replica_num=replica_num,
                registered=True,
            )

        run_spec: RunSpec = RunSpec.__response__.parse_raw(run.run_spec)
        assert isinstance(run_spec.configuration, ServiceConfiguration)
        run_spec.configuration.image = "new"
        run.run_spec = run_spec.json()
        run.deployment_num += 1
        await session.commit()

        await process_runs.process_runs()
        await session.refresh(run)
        assert run.status == RunStatus.RUNNING
        assert len(run.jobs) == 3
        # old replicas remain as-is
        for replica_num in range(2):
            assert run.jobs[replica_num].status == JobStatus.RUNNING
            assert run.jobs[replica_num].replica_num == replica_num
            assert run.jobs[replica_num].deployment_num == 0
            assert (
                cast(
                    JobSpec, JobSpec.__response__.parse_raw(run.jobs[replica_num].job_spec_data)
                ).image_name
                == "old"
            )
        # an extra replica is submitted
        assert run.jobs[2].status == JobStatus.SUBMITTED
        assert run.jobs[2].replica_num == 2
        assert run.jobs[2].deployment_num == 1
        assert (
            cast(JobSpec, JobSpec.__response__.parse_raw(run.jobs[2].job_spec_data)).image_name
            == "new"
        )

    @pytest.mark.parametrize(
        "new_replica_status",
        [JobStatus.SUBMITTED, JobStatus.PROVISIONING, JobStatus.PULLING, JobStatus.RUNNING],
    )
    async def test_not_stops_out_of_date_replica_until_new_replica_is_registered(
        self, test_db, session: AsyncSession, new_replica_status: JobStatus
    ) -> None:
        run = await make_run(session, status=RunStatus.RUNNING, replicas=2, image="old")
        for replica_num in range(2):
            await create_job(
                session=session,
                run=run,
                status=JobStatus.RUNNING,
                replica_num=replica_num,
                registered=True,
            )

        run_spec: RunSpec = RunSpec.__response__.parse_raw(run.run_spec)
        assert isinstance(run_spec.configuration, ServiceConfiguration)
        run_spec.configuration.image = "new"
        run.run_spec = run_spec.json()
        run.deployment_num += 1
        await create_job(
            session=session,
            run=run,
            status=new_replica_status,
            replica_num=2,
            registered=False,
        )
        await session.commit()

        await process_runs.process_runs()
        await session.refresh(run)
        assert run.status == RunStatus.RUNNING
        assert len(run.jobs) == 3
        # All replicas remain as-is:
        # - cannot yet start a new replica - there are already 3 non-terminated replicas
        #   (3 = 2 desired + 1 max_surge)
        # - cannot yet stop an out-of-date replica - that would only leave one registered replica,
        #   which is less than the desired count (2)
        for replica_num in range(2):
            assert run.jobs[replica_num].status == JobStatus.RUNNING
            assert run.jobs[replica_num].replica_num == replica_num
            assert run.jobs[replica_num].deployment_num == 0
            assert (
                cast(
                    JobSpec, JobSpec.__response__.parse_raw(run.jobs[replica_num].job_spec_data)
                ).image_name
                == "old"
            )
        assert run.jobs[2].status == new_replica_status
        assert run.jobs[2].replica_num == 2
        assert run.jobs[2].deployment_num == 1
        assert (
            cast(JobSpec, JobSpec.__response__.parse_raw(run.jobs[2].job_spec_data)).image_name
            == "new"
        )

    async def test_stops_out_of_date_replica(self, test_db, session: AsyncSession) -> None:
        run = await make_run(session, status=RunStatus.RUNNING, replicas=2, image="old")
        for replica_num in range(2):
            await create_job(
                session=session,
                run=run,
                status=JobStatus.RUNNING,
                replica_num=replica_num,
                registered=True,
            )

        run_spec: RunSpec = RunSpec.__response__.parse_raw(run.run_spec)
        assert isinstance(run_spec.configuration, ServiceConfiguration)
        run_spec.configuration.image = "new"
        run.run_spec = run_spec.json()
        run.deployment_num += 1
        await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            replica_num=2,
            registered=True,
        )
        await session.commit()

        await process_runs.process_runs()
        await session.refresh(run)
        assert run.status == RunStatus.RUNNING
        assert len(run.jobs) == 3
        # one old replica remains as-is
        assert run.jobs[0].status == JobStatus.RUNNING
        assert run.jobs[0].replica_num == 0
        assert run.jobs[0].deployment_num == 0
        assert (
            cast(JobSpec, JobSpec.__response__.parse_raw(run.jobs[0].job_spec_data)).image_name
            == "old"
        )
        # another old replica is terminated
        assert run.jobs[1].status == JobStatus.TERMINATING
        assert run.jobs[1].termination_reason == JobTerminationReason.SCALED_DOWN
        assert run.jobs[1].replica_num == 1
        assert run.jobs[1].deployment_num == 0
        assert (
            cast(JobSpec, JobSpec.__response__.parse_raw(run.jobs[1].job_spec_data)).image_name
            == "old"
        )
        # the new replica remains as-is
        assert run.jobs[2].status == JobStatus.RUNNING
        assert run.jobs[2].replica_num == 2
        assert run.jobs[2].deployment_num == 1
        assert (
            cast(JobSpec, JobSpec.__response__.parse_raw(run.jobs[2].job_spec_data)).image_name
            == "new"
        )

    @pytest.mark.parametrize("out_of_date_replica_still_registered", [True, False])
    async def test_not_starts_new_replica_until_out_of_date_replica_terminated(
        self, test_db, session: AsyncSession, out_of_date_replica_still_registered: bool
    ) -> None:
        run = await make_run(session, status=RunStatus.RUNNING, replicas=2, image="old")
        await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            replica_num=0,
            registered=True,
        )
        await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            termination_reason=JobTerminationReason.SCALED_DOWN,
            replica_num=1,
            registered=out_of_date_replica_still_registered,
        )

        run_spec: RunSpec = RunSpec.__response__.parse_raw(run.run_spec)
        assert isinstance(run_spec.configuration, ServiceConfiguration)
        run_spec.configuration.image = "new"
        run.run_spec = run_spec.json()
        run.deployment_num += 1
        await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            replica_num=2,
            registered=True,
        )
        await session.commit()

        await process_runs.process_runs()
        await session.refresh(run)
        assert run.status == RunStatus.RUNNING
        assert len(run.jobs) == 3
        # All replicas remain as-is:
        # - cannot yet start a new replica - there are already 3 non-terminated replicas
        #   (3 = 2 desired + 1 max_surge)
        # - cannot yet stop an out-of-date replica - that would only leave one registered replica,
        #   which is less than the desired count (2)
        assert run.jobs[0].status == JobStatus.RUNNING
        assert run.jobs[0].replica_num == 0
        assert run.jobs[0].deployment_num == 0
        assert (
            cast(JobSpec, JobSpec.__response__.parse_raw(run.jobs[0].job_spec_data)).image_name
            == "old"
        )
        assert run.jobs[1].status == JobStatus.TERMINATING
        assert run.jobs[1].termination_reason == JobTerminationReason.SCALED_DOWN
        assert run.jobs[1].replica_num == 1
        assert run.jobs[1].deployment_num == 0
        assert (
            cast(JobSpec, JobSpec.__response__.parse_raw(run.jobs[1].job_spec_data)).image_name
            == "old"
        )
        assert run.jobs[2].status == JobStatus.RUNNING
        assert run.jobs[2].replica_num == 2
        assert run.jobs[2].deployment_num == 1
        assert (
            cast(JobSpec, JobSpec.__response__.parse_raw(run.jobs[2].job_spec_data)).image_name
            == "new"
        )

    async def test_reuses_vacant_replica_num_when_starting_new_replica(
        self, test_db, session: AsyncSession
    ) -> None:
        run = await make_run(session, status=RunStatus.RUNNING, replicas=2, image="old")
        await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            replica_num=0,
            registered=True,
        )
        await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATED,
            termination_reason=JobTerminationReason.SCALED_DOWN,
            replica_num=1,
            registered=False,
        )

        run_spec: RunSpec = RunSpec.__response__.parse_raw(run.run_spec)
        assert isinstance(run_spec.configuration, ServiceConfiguration)
        run_spec.configuration.image = "new"
        run.run_spec = run_spec.json()
        run.deployment_num += 1
        await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            replica_num=2,
            registered=True,
        )
        await session.commit()

        await process_runs.process_runs()
        await session.refresh(run)
        run.jobs.sort(key=lambda j: (j.replica_num, j.submission_num))
        assert run.status == RunStatus.RUNNING
        assert len(run.jobs) == 4  # 3 active submissions, 1 terminated submission
        # The running old replica remains as-is
        assert run.jobs[0].status == JobStatus.RUNNING
        assert run.jobs[0].replica_num == 0
        assert run.jobs[0].deployment_num == 0
        assert (
            cast(JobSpec, JobSpec.__response__.parse_raw(run.jobs[0].job_spec_data)).image_name
            == "old"
        )
        # The terminated old replica remains as-is
        assert run.jobs[1].status == JobStatus.TERMINATED
        assert run.jobs[1].termination_reason == JobTerminationReason.SCALED_DOWN
        assert run.jobs[1].replica_num == 1
        assert run.jobs[1].deployment_num == 0
        assert run.jobs[1].submission_num == 0
        assert (
            cast(JobSpec, JobSpec.__response__.parse_raw(run.jobs[1].job_spec_data)).image_name
            == "old"
        )
        # The replica_num of the terminated old replica (1) is reused for the new replica
        assert run.jobs[2].status == JobStatus.SUBMITTED
        assert run.jobs[2].replica_num == 1
        assert run.jobs[2].deployment_num == 1
        assert run.jobs[2].submission_num == 1
        assert (
            cast(JobSpec, JobSpec.__response__.parse_raw(run.jobs[2].job_spec_data)).image_name
            == "new"
        )
        # The running new replica remains as-is
        assert run.jobs[3].status == JobStatus.RUNNING
        assert run.jobs[3].replica_num == 2
        assert run.jobs[3].deployment_num == 1
        assert (
            cast(JobSpec, JobSpec.__response__.parse_raw(run.jobs[3].job_spec_data)).image_name
            == "new"
        )

    @pytest.mark.parametrize(
        "new_replica_status", [JobStatus.SUBMITTED, JobStatus.PROVISIONING, JobStatus.PULLING]
    )
    async def test_stops_unregistered_out_of_date_replicas_unconditionally(
        self, test_db, session: AsyncSession, new_replica_status: JobStatus
    ) -> None:
        run = await make_run(session, status=RunStatus.PROVISIONING, replicas=2, image="old")
        for replica_num in range(2):
            await create_job(
                session=session,
                run=run,
                status=JobStatus.PULLING,
                replica_num=replica_num,
                registered=False,
            )

        run_spec: RunSpec = RunSpec.__response__.parse_raw(run.run_spec)
        assert isinstance(run_spec.configuration, ServiceConfiguration)
        run_spec.configuration.image = "new"
        run.run_spec = run_spec.json()
        run.deployment_num += 1
        await create_job(
            session=session,
            run=run,
            status=new_replica_status,
            replica_num=2,
            registered=False,
        )
        await session.commit()

        await process_runs.process_runs()
        await session.refresh(run)
        assert run.status == RunStatus.PROVISIONING
        assert len(run.jobs) == 3
        # The two out of date replicas transition from pulling to terminating immediately.
        # No need to keep these unregistered replicas - they don't contribute to the desired count.
        assert run.jobs[0].status == JobStatus.TERMINATING
        assert run.jobs[0].replica_num == 0
        assert run.jobs[0].deployment_num == 0
        assert (
            cast(JobSpec, JobSpec.__response__.parse_raw(run.jobs[0].job_spec_data)).image_name
            == "old"
        )
        assert run.jobs[1].status == JobStatus.TERMINATING
        assert run.jobs[1].termination_reason == JobTerminationReason.SCALED_DOWN
        assert run.jobs[1].replica_num == 1
        assert run.jobs[1].deployment_num == 0
        assert (
            cast(JobSpec, JobSpec.__response__.parse_raw(run.jobs[1].job_spec_data)).image_name
            == "old"
        )
        # The new replica remains as-is
        assert run.jobs[2].status == new_replica_status
        assert run.jobs[2].replica_num == 2
        assert run.jobs[2].deployment_num == 1
        assert (
            cast(JobSpec, JobSpec.__response__.parse_raw(run.jobs[2].job_spec_data)).image_name
            == "new"
        )


# TODO(egor-s): TestProcessRunsMultiNode
# TODO(egor-s): TestProcessRunsAutoScaling
