from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.runs import JobStatus
from dstack._internal.server.background.tasks.process_pending_jobs import process_pending_jobs
from dstack._internal.server.testing.common import (
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
)


class TestProcessPendingJobs:
    @pytest.mark.asyncio
    async def test_transitions_pending_jobs_to_submitted(self, test_db, session: AsyncSession):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
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
            status=JobStatus.PENDING,
        )
        with patch("dstack._internal.utils.common.get_current_datetime") as datetime_mock:
            datetime_mock.return_value = datetime(2023, 1, 2, 3, 30, 0, tzinfo=timezone.utc)
            await process_pending_jobs()
        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.SUBMITTED
