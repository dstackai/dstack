from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.runs import JobStatus
from dstack._internal.server.background.tasks.process_terminating_jobs import (
    process_terminating_jobs,
)
from tests._internal.server.common import (
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
)

MODULE = "dstack._internal.server.background.tasks.process_terminating_jobs"


class TestProcessTerminatingJobs:
    @pytest.mark.asyncio
    async def test_transitions_terminating_jobs_to_terminated(
        self, test_db, session: AsyncSession
    ):
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
            status=JobStatus.TERMINATING,
        )
        with patch(f"{MODULE}.get_current_datetime") as datetime_mock, patch(
            f"{MODULE}.terminate_job_submission_instance"
        ):
            datetime_mock.return_value = datetime(2023, 1, 2, 3, 4, 15 + 1, tzinfo=timezone.utc)
            await process_terminating_jobs()
        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.TERMINATED
