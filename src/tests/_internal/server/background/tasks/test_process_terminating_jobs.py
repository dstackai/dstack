from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import InstanceType, Resources
from dstack._internal.core.models.runs import JobProvisioningData, JobStatus
from dstack._internal.server.background.tasks.process_finished_jobs import process_finished_jobs
from dstack._internal.server.testing.common import (
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
)

MODULE = "dstack._internal.server.background.tasks.process_finished_jobs"


class TestProcessFinishedJobs:
    @pytest.mark.asyncio
    async def test_transitions_done_jobs_marked_as_removed(self, test_db, session: AsyncSession):
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
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.DONE,
            job_provisioning_data=JobProvisioningData(
                backend=BackendType.LOCAL,
                instance_type=InstanceType(
                    name="local", resources=Resources(cpus=1, memory_mib=1024, gpus=[], spot=False)
                ),
                instance_id="0000-0000",
                hostname="localhost",
                region="",
                price=0.0,
                username="root",
                ssh_port=22,
                dockerized=False,
            ),
        )
        with patch(f"{MODULE}.terminate_job_submission_instance") as terminate:
            await process_finished_jobs()
            terminate.assert_called_once()
        await session.refresh(job)
        assert job is not None
        assert job.removed
