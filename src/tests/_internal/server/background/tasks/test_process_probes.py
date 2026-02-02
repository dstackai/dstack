from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from freezegun import freeze_time
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.configurations import ProbeConfig, ServiceConfiguration
from dstack._internal.core.models.instances import InstanceStatus
from dstack._internal.core.models.runs import JobStatus
from dstack._internal.server.background.tasks.process_probes import (
    PROCESSING_OVERHEAD_TIMEOUT,
    SSH_CONNECT_TIMEOUT,
    process_probes,
)
from dstack._internal.server.testing.common import (
    create_instance,
    create_job,
    create_probe,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_job_provisioning_data,
    get_run_spec,
)

pytestmark = pytest.mark.usefixtures("image_config_mock")


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestProcessProbes:
    async def test_deactivates_probes_for_stopped_job(
        self, test_db, session: AsyncSession
    ) -> None:
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_spec=get_run_spec(
                run_name="test",
                repo_id=repo.name,
                configuration=ServiceConfiguration(
                    port=80,
                    image="nginx",
                    probes=[
                        ProbeConfig(type="http", url="/1"),
                        ProbeConfig(type="http", url="/2"),
                    ],
                ),
            ),
        )
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
        )
        running_job = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            job_provisioning_data=get_job_provisioning_data(),
            instance=instance,
            instance_assigned=True,
        )
        terminating_job = await create_job(
            session=session,
            run=run,
            status=JobStatus.TERMINATING,
            job_provisioning_data=get_job_provisioning_data(),
            instance=instance,
            instance_assigned=True,
        )
        running_job_probes = [
            await create_probe(session, running_job, probe_num=i) for i in range(2)
        ]
        terminating_job_probes = [
            await create_probe(session, terminating_job, probe_num=i) for i in range(2)
        ]
        await process_probes()
        for probe in running_job_probes:
            await session.refresh(probe)
            assert probe.active
        for probe in terminating_job_probes:
            await session.refresh(probe)
            assert not probe.active

    async def test_schedules_probe_execution(self, test_db, session: AsyncSession) -> None:
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_spec=get_run_spec(
                run_name="test",
                repo_id=repo.name,
                configuration=ServiceConfiguration(
                    port=80,
                    image="nginx",
                    probes=[
                        ProbeConfig(type="http", url="/1", timeout="1m"),
                        ProbeConfig(type="http", url="/2", timeout="2m"),
                    ],
                ),
            ),
        )
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            job_provisioning_data=get_job_provisioning_data(),
            instance=instance,
            instance_assigned=True,
        )
        probe_1 = await create_probe(
            session, job, probe_num=0, due=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        )
        probe_2 = await create_probe(
            session, job, probe_num=1, due=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        )
        processing_time = datetime(2025, 1, 1, 0, 0, 1, tzinfo=timezone.utc)
        with freeze_time(processing_time):
            with patch(
                "dstack._internal.server.background.tasks.process_probes.PROBES_SCHEDULER"
            ) as scheduler_mock:
                await process_probes()
                assert scheduler_mock.add_job.call_count == 2
        await session.refresh(probe_1)
        assert probe_1.active
        assert (
            probe_1.due
            == processing_time
            + timedelta(minutes=1)
            + SSH_CONNECT_TIMEOUT
            + PROCESSING_OVERHEAD_TIMEOUT
        )
        await session.refresh(probe_2)
        assert probe_2.active
        assert (
            probe_2.due
            == processing_time
            + timedelta(minutes=2)
            + SSH_CONNECT_TIMEOUT
            + PROCESSING_OVERHEAD_TIMEOUT
        )

    async def test_deactivates_probe_when_until_ready_and_ready_after_reached(
        self, test_db, session: AsyncSession
    ) -> None:
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_spec=get_run_spec(
                run_name="test",
                repo_id=repo.name,
                configuration=ServiceConfiguration(
                    port=80,
                    image="nginx",
                    probes=[
                        ProbeConfig(
                            type="http", url="/until_ready", until_ready=True, ready_after=3
                        ),
                        ProbeConfig(type="http", url="/regular", until_ready=False, ready_after=3),
                    ],
                ),
            ),
        )
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            job_provisioning_data=get_job_provisioning_data(),
            instance=instance,
            instance_assigned=True,
        )

        probe_until_ready = await create_probe(session, job, probe_num=0, success_streak=3)
        probe_regular = await create_probe(session, job, probe_num=1, success_streak=3)

        with patch(
            "dstack._internal.server.background.tasks.process_probes.PROBES_SCHEDULER"
        ) as scheduler_mock:
            await process_probes()

        await session.refresh(probe_until_ready)
        await session.refresh(probe_regular)

        assert not probe_until_ready.active
        assert probe_until_ready.success_streak == 3

        assert probe_regular.active
        assert probe_regular.success_streak == 3
        assert scheduler_mock.add_job.call_count == 1  # only the regular probe was scheduled


# TODO: test probe success and failure
# (skipping for now - a bit difficult to test and most of the logic will be mocked)
