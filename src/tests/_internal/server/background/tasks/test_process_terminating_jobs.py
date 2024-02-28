from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import InstanceType, Resources
from dstack._internal.core.models.runs import InstanceStatus, JobProvisioningData, JobStatus
from dstack._internal.server.background.tasks.process_finished_jobs import process_finished_jobs
from dstack._internal.server.testing.common import (
    create_instance,
    create_job,
    create_pool,
    create_project,
    create_repo,
    create_run,
    create_user,
)


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
        pool = await create_pool(session, project)
        instance = await create_instance(
            session=session,
            project=project,
            pool=pool,
            status=InstanceStatus.IDLE,
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.DONE,
            instance=instance,
            job_provisioning_data=JobProvisioningData(
                backend=BackendType.AWS,
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
                backend_data=None,
                ssh_proxy=None,
            ),
        )
        with patch("dstack._internal.server.background.tasks.process_finished_jobs.submit_stop"):
            await process_finished_jobs()
        await session.refresh(job)
        assert job is not None
        assert job.removed
