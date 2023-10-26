from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.server import settings
from dstack._internal.server.schemas.runner import LogEvent
from dstack._internal.server.services.logs import write_logs
from dstack._internal.server.testing.common import create_project


class TestWriteLogs:
    @pytest.mark.asyncio
    async def test_writes_logs(self, test_db, session: AsyncSession, tmp_path: Path):
        project = await create_project(session=session)
        with patch.object(settings, "SERVER_DIR_PATH", tmp_path):
            write_logs(
                project=project,
                run_name="test_run",
                job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
                runner_logs=[
                    LogEvent(timestamp=1696586513234234123, message=b"Hello"),
                    LogEvent(timestamp=1696586513234235123, message=b"World"),
                ],
                job_logs=[],
            )
        runner_log_path = (
            tmp_path
            / "projects"
            / project.name
            / "logs"
            / "test_run"
            / "1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"
            / "runner.log"
        )
        assert runner_log_path.read_text() == (
            '{"timestamp": "2023-10-06T10:01:53.234234+00:00", "log_source": "stdout", "message": "SGVsbG8="}\n'
            '{"timestamp": "2023-10-06T10:01:53.234235+00:00", "log_source": "stdout", "message": "V29ybGQ="}\n'
        )
