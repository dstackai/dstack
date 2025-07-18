import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List
from unittest.mock import Mock, call
from uuid import UUID

import botocore.exceptions
import pytest
import pytest_asyncio
from freezegun import freeze_time
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.logs import LogEvent, LogEventSource, LogProducer
from dstack._internal.server.models import ProjectModel
from dstack._internal.server.schemas.logs import PollLogsRequest
from dstack._internal.server.schemas.runner import LogEvent as RunnerLogEvent
from dstack._internal.server.services.logs.aws import (
    CloudWatchLogStorage,
)
from dstack._internal.server.services.logs.base import LogStorageError
from dstack._internal.server.services.logs.filelog import FileLogStorage
from dstack._internal.server.testing.common import create_project


class TestFileLogStorage:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_writes_logs(self, test_db, session: AsyncSession, tmp_path: Path):
        project = await create_project(session=session)
        log_storage = FileLogStorage(tmp_path)
        log_storage.write_logs(
            project=project,
            run_name="test_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            runner_logs=[
                RunnerLogEvent(timestamp=1696586513234, message=b"Hello"),
                RunnerLogEvent(timestamp=1696586513235, message=b"World"),
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
            '{"timestamp":"2023-10-06T10:01:53.234000+00:00","log_source":"stdout","message":"Hello"}\n'
            '{"timestamp":"2023-10-06T10:01:53.235000+00:00","log_source":"stdout","message":"World"}\n'
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_poll_logs_basic(self, test_db, session: AsyncSession, tmp_path: Path):
        project = await create_project(session=session)
        log_storage = FileLogStorage(tmp_path)

        # Write test logs
        log_storage.write_logs(
            project=project,
            run_name="test_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            runner_logs=[
                RunnerLogEvent(timestamp=1696586513234, message=b"Log1"),
                RunnerLogEvent(timestamp=1696586513235, message=b"Log2"),
                RunnerLogEvent(timestamp=1696586513236, message=b"Log3"),
            ],
            job_logs=[],
        )

        # Test basic polling without pagination
        poll_request = PollLogsRequest(
            run_name="test_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            limit=10,
            diagnose=True,
        )
        job_submission_logs = log_storage.poll_logs(project, poll_request)

        assert len(job_submission_logs.logs) == 3
        assert job_submission_logs.next_token is None  # No more logs, so no next_token

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_poll_logs_with_next_token_pagination(
        self, test_db, session: AsyncSession, tmp_path: Path
    ):
        project = await create_project(session=session)
        log_storage = FileLogStorage(tmp_path)

        # Write test logs
        log_storage.write_logs(
            project=project,
            run_name="test_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            runner_logs=[
                RunnerLogEvent(timestamp=1696586513234, message=b"Log1"),
                RunnerLogEvent(timestamp=1696586513235, message=b"Log2"),
                RunnerLogEvent(timestamp=1696586513236, message=b"Log3"),
                RunnerLogEvent(timestamp=1696586513237, message=b"Log4"),
                RunnerLogEvent(timestamp=1696586513238, message=b"Log5"),
            ],
            job_logs=[],
        )

        # First page: get 2 logs
        poll_request = PollLogsRequest(
            run_name="test_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            limit=2,
            diagnose=True,
        )
        job_submission_logs = log_storage.poll_logs(project, poll_request)

        assert len(job_submission_logs.logs) == 2
        assert job_submission_logs.logs[0].message == "Log1"
        assert job_submission_logs.logs[1].message == "Log2"
        assert job_submission_logs.next_token == "2"  # Next line to read

        # Second page: use next_token
        poll_request.next_token = job_submission_logs.next_token
        job_submission_logs = log_storage.poll_logs(project, poll_request)

        assert len(job_submission_logs.logs) == 2
        assert job_submission_logs.logs[0].message == "Log3"
        assert job_submission_logs.logs[1].message == "Log4"
        assert job_submission_logs.next_token == "4"  # Next line to read

        # Third page: get remaining log
        poll_request.next_token = job_submission_logs.next_token
        job_submission_logs = log_storage.poll_logs(project, poll_request)

        assert len(job_submission_logs.logs) == 1
        assert job_submission_logs.logs[0].message == "Log5"
        assert job_submission_logs.next_token is None  # No more logs

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_poll_logs_with_start_from_specific_line(
        self, test_db, session: AsyncSession, tmp_path: Path
    ):
        project = await create_project(session=session)
        log_storage = FileLogStorage(tmp_path)

        # Write test logs
        log_storage.write_logs(
            project=project,
            run_name="test_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            runner_logs=[
                RunnerLogEvent(timestamp=1696586513234, message=b"Log1"),
                RunnerLogEvent(timestamp=1696586513235, message=b"Log2"),
                RunnerLogEvent(timestamp=1696586513236, message=b"Log3"),
            ],
            job_logs=[],
        )

        # Start from line 1 (second log)
        poll_request = PollLogsRequest(
            run_name="test_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            next_token="1",
            limit=10,
            diagnose=True,
        )
        job_submission_logs = log_storage.poll_logs(project, poll_request)

        assert len(job_submission_logs.logs) == 2
        assert job_submission_logs.logs[0].message == "Log2"
        assert job_submission_logs.logs[1].message == "Log3"
        assert job_submission_logs.next_token is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_poll_logs_invalid_next_token_raises_error(
        self, test_db, session: AsyncSession, tmp_path: Path
    ):
        project = await create_project(session=session)
        log_storage = FileLogStorage(tmp_path)

        # Test with non-integer next_token
        poll_request = PollLogsRequest(
            run_name="test_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            next_token="invalid",
            limit=10,
            diagnose=True,
        )
        with pytest.raises(ServerClientError):
            log_storage.poll_logs(project, poll_request)

        # Test with negative next_token
        poll_request.next_token = "-1"
        with pytest.raises(ServerClientError):
            log_storage.poll_logs(project, poll_request)

        # Test with float next_token
        poll_request.next_token = "1.5"
        with pytest.raises(ServerClientError):
            log_storage.poll_logs(project, poll_request)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_poll_logs_file_not_found_raises_no_error(
        self, test_db, session: AsyncSession, tmp_path: Path
    ):
        project = await create_project(session=session)
        log_storage = FileLogStorage(tmp_path)

        # Test with non-existent log file
        poll_request = PollLogsRequest(
            run_name="nonexistent_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            limit=10,
            diagnose=True,
        )
        log_storage.poll_logs(project, poll_request)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_poll_logs_with_time_filtering_and_pagination(
        self, test_db, session: AsyncSession, tmp_path: Path
    ):
        project = await create_project(session=session)
        log_storage = FileLogStorage(tmp_path)

        # Write test logs with different timestamps
        log_storage.write_logs(
            project=project,
            run_name="test_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            runner_logs=[
                RunnerLogEvent(
                    timestamp=1696586513234, message=b"Log1"
                ),  # 2023-10-06T10:01:53.234
                RunnerLogEvent(
                    timestamp=1696586513235, message=b"Log2"
                ),  # 2023-10-06T10:01:53.235
                RunnerLogEvent(
                    timestamp=1696586513236, message=b"Log3"
                ),  # 2023-10-06T10:01:53.236
                RunnerLogEvent(
                    timestamp=1696586513237, message=b"Log4"
                ),  # 2023-10-06T10:01:53.237
            ],
            job_logs=[],
        )

        # Filter logs after 2023-10-06T10:01:53.235 with pagination
        poll_request = PollLogsRequest(
            run_name="test_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            start_time=datetime(2023, 10, 6, 10, 1, 53, 235000, timezone.utc),
            limit=1,
            diagnose=True,
        )
        job_submission_logs = log_storage.poll_logs(project, poll_request)

        # Should get Log3 first (timestamp > 235)
        assert len(job_submission_logs.logs) == 1
        assert job_submission_logs.logs[0].message == "Log3"
        assert job_submission_logs.next_token == "3"

        # Get next page
        poll_request.next_token = job_submission_logs.next_token
        job_submission_logs = log_storage.poll_logs(project, poll_request)

        # Should get Log4
        assert len(job_submission_logs.logs) == 1
        assert job_submission_logs.logs[0].message == "Log4"
        # Should not have next_token since we reached end of file
        assert job_submission_logs.next_token is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_poll_logs_empty_file_returns_empty_list(
        self, test_db, session: AsyncSession, tmp_path: Path
    ):
        project = await create_project(session=session)
        log_storage = FileLogStorage(tmp_path)

        # Create empty log file
        log_file_path = (
            tmp_path
            / "projects"
            / project.name
            / "logs"
            / "test_run"
            / "1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"
            / "runner.log"
        )
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        log_file_path.write_text("")

        poll_request = PollLogsRequest(
            run_name="test_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            limit=10,
            diagnose=True,
        )
        job_submission_logs = log_storage.poll_logs(project, poll_request)

        assert len(job_submission_logs.logs) == 0
        assert job_submission_logs.next_token is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_next_token_pagination_complete_workflow(
        self, test_db, session: AsyncSession, tmp_path: Path
    ):
        """Test complete pagination workflow using next_token"""
        project = await create_project(session=session)
        log_storage = FileLogStorage(tmp_path)

        # Write 10 logs
        log_storage.write_logs(
            project=project,
            run_name="test_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            runner_logs=[
                RunnerLogEvent(timestamp=1696586513000 + i, message=f"Log{i + 1}".encode())
                for i in range(10)
            ],
            job_logs=[],
        )

        # First page: get 3 logs
        poll_request = PollLogsRequest(
            run_name="test_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            limit=3,
            diagnose=True,
        )
        page1 = log_storage.poll_logs(project, poll_request)

        assert len(page1.logs) == 3
        assert page1.logs[0].message == "Log1"
        assert page1.logs[1].message == "Log2"
        assert page1.logs[2].message == "Log3"
        assert page1.next_token == "3"  # Next line to read

        # Second page: use next_token
        poll_request.next_token = page1.next_token
        page2 = log_storage.poll_logs(project, poll_request)

        assert len(page2.logs) == 3
        assert page2.logs[0].message == "Log4"
        assert page2.logs[1].message == "Log5"
        assert page2.logs[2].message == "Log6"
        assert page2.next_token == "6"

        # Third page: get more logs
        poll_request.next_token = page2.next_token
        page3 = log_storage.poll_logs(project, poll_request)

        assert len(page3.logs) == 3
        assert page3.logs[0].message == "Log7"
        assert page3.logs[1].message == "Log8"
        assert page3.logs[2].message == "Log9"
        assert page3.next_token == "9"

        # Fourth page: get last log
        poll_request.next_token = page3.next_token
        page4 = log_storage.poll_logs(project, poll_request)

        assert len(page4.logs) == 1
        assert page4.logs[0].message == "Log10"
        assert page4.next_token is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_next_token_with_time_filtering(
        self, test_db, session: AsyncSession, tmp_path: Path
    ):
        """Test next_token behavior with time filtering"""
        project = await create_project(session=session)
        log_storage = FileLogStorage(tmp_path)

        # Write logs with different timestamps
        log_storage.write_logs(
            project=project,
            run_name="test_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            runner_logs=[
                RunnerLogEvent(timestamp=1696586513000, message=b"Log1"),  # Before filter
                RunnerLogEvent(timestamp=1696586513100, message=b"Log2"),  # Before filter
                RunnerLogEvent(timestamp=1696586513200, message=b"Log3"),  # After filter
                RunnerLogEvent(timestamp=1696586513300, message=b"Log4"),  # After filter
                RunnerLogEvent(timestamp=1696586513400, message=b"Log5"),  # After filter
            ],
            job_logs=[],
        )

        # Filter logs after timestamp 150 with pagination
        start_time = datetime.fromtimestamp(1696586513.150, tz=timezone.utc)
        poll_request = PollLogsRequest(
            run_name="test_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            start_time=start_time,
            limit=2,
            diagnose=True,
        )

        page1 = log_storage.poll_logs(project, poll_request)
        assert len(page1.logs) == 2
        assert page1.logs[0].message == "Log3"
        assert page1.logs[1].message == "Log4"
        assert page1.next_token == "4"

        # Get next page
        poll_request.next_token = page1.next_token
        page2 = log_storage.poll_logs(project, poll_request)
        assert len(page2.logs) == 1
        assert page2.logs[0].message == "Log5"
        assert page2.next_token is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_next_token_edge_cases(self, test_db, session: AsyncSession, tmp_path: Path):
        """Test edge cases for next_token behavior"""
        project = await create_project(session=session)
        log_storage = FileLogStorage(tmp_path)

        # Write exactly one log
        log_storage.write_logs(
            project=project,
            run_name="test_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            runner_logs=[
                RunnerLogEvent(timestamp=1696586513000, message=b"OnlyLog"),
            ],
            job_logs=[],
        )

        # Request with limit higher than available logs
        poll_request = PollLogsRequest(
            run_name="test_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            limit=10,
            diagnose=True,
        )
        result = log_storage.poll_logs(project, poll_request)

        assert len(result.logs) == 1
        assert result.logs[0].message == "OnlyLog"
        assert result.next_token is None

        # Request with limit equal to available logs
        poll_request.limit = 1
        result = log_storage.poll_logs(project, poll_request)

        assert len(result.logs) == 1
        assert result.logs[0].message == "OnlyLog"
        assert result.next_token is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_next_token_beyond_file_end(
        self, test_db, session: AsyncSession, tmp_path: Path
    ):
        """Test next_token that points beyond the end of file"""
        project = await create_project(session=session)
        log_storage = FileLogStorage(tmp_path)

        # Write 3 logs
        log_storage.write_logs(
            project=project,
            run_name="test_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            runner_logs=[
                RunnerLogEvent(timestamp=1696586513000, message=b"Log1"),
                RunnerLogEvent(timestamp=1696586513100, message=b"Log2"),
                RunnerLogEvent(timestamp=1696586513200, message=b"Log3"),
            ],
            job_logs=[],
        )

        # Use next_token that points beyond the file
        poll_request = PollLogsRequest(
            run_name="test_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            next_token="10",  # Points beyond the 3 logs in file
            limit=5,
            diagnose=True,
        )
        result = log_storage.poll_logs(project, poll_request)

        assert len(result.logs) == 0
        assert result.next_token is None


class TestPollLogsRequestValidation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_poll_logs_descending_basic(
        self, test_db, session: AsyncSession, tmp_path: Path
    ):
        """Test basic descending log polling functionality."""
        project = await create_project(session=session)
        log_storage = FileLogStorage(tmp_path)

        # Write test logs
        log_storage.write_logs(
            project=project,
            run_name="test_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            runner_logs=[
                RunnerLogEvent(timestamp=1696586513234, message=b"Log1"),
                RunnerLogEvent(timestamp=1696586513235, message=b"Log2"),
                RunnerLogEvent(timestamp=1696586513236, message=b"Log3"),
                RunnerLogEvent(timestamp=1696586513237, message=b"Log4"),
                RunnerLogEvent(timestamp=1696586513238, message=b"Log5"),
            ],
            job_logs=[],
        )

        # Test descending polling
        poll_request = PollLogsRequest(
            run_name="test_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            limit=10,
            diagnose=True,
            descending=True,
        )
        job_submission_logs = log_storage.poll_logs(project, poll_request)

        # Should return logs in descending order (newest first)
        assert len(job_submission_logs.logs) == 5
        assert job_submission_logs.logs[0].message == "Log5"
        assert job_submission_logs.logs[1].message == "Log4"
        assert job_submission_logs.logs[2].message == "Log3"
        assert job_submission_logs.logs[3].message == "Log2"
        assert job_submission_logs.logs[4].message == "Log1"
        assert job_submission_logs.next_token is None  # All logs returned

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_poll_logs_descending_with_limit(
        self, test_db, session: AsyncSession, tmp_path: Path
    ):
        """Test descending log polling with limit smaller than total logs."""
        project = await create_project(session=session)
        log_storage = FileLogStorage(tmp_path)

        # Write test logs
        log_storage.write_logs(
            project=project,
            run_name="test_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            runner_logs=[
                RunnerLogEvent(timestamp=1696586513234, message=b"Log1"),
                RunnerLogEvent(timestamp=1696586513235, message=b"Log2"),
                RunnerLogEvent(timestamp=1696586513236, message=b"Log3"),
                RunnerLogEvent(timestamp=1696586513237, message=b"Log4"),
                RunnerLogEvent(timestamp=1696586513238, message=b"Log5"),
            ],
            job_logs=[],
        )

        # Test with limit smaller than total logs
        poll_request = PollLogsRequest(
            run_name="test_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            limit=3,
            diagnose=True,
            descending=True,
        )
        job_submission_logs = log_storage.poll_logs(project, poll_request)

        # Should return only the last 3 logs in descending order
        assert len(job_submission_logs.logs) == 3
        assert job_submission_logs.logs[0].message == "Log5"
        assert job_submission_logs.logs[1].message == "Log4"
        assert job_submission_logs.logs[2].message == "Log3"
        # Should have next_token for pagination
        assert job_submission_logs.next_token is not None

        # Test next page
        poll_request.next_token = job_submission_logs.next_token
        job_submission_logs = log_storage.poll_logs(project, poll_request)

        # Should return remaining logs in descending order
        assert len(job_submission_logs.logs) == 2
        assert job_submission_logs.logs[0].message == "Log2"
        assert job_submission_logs.logs[1].message == "Log1"
        assert job_submission_logs.next_token is None  # No more logs

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_poll_logs_descending_with_time_filtering(
        self, test_db, session: AsyncSession, tmp_path: Path
    ):
        """Test descending log polling with time filtering."""
        project = await create_project(session=session)
        log_storage = FileLogStorage(tmp_path)

        # Write test logs with different timestamps
        log_storage.write_logs(
            project=project,
            run_name="test_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            runner_logs=[
                RunnerLogEvent(
                    timestamp=1696586513234, message=b"Log1"
                ),  # 2023-10-06T10:01:53.234
                RunnerLogEvent(
                    timestamp=1696586513235, message=b"Log2"
                ),  # 2023-10-06T10:01:53.235
                RunnerLogEvent(
                    timestamp=1696586513236, message=b"Log3"
                ),  # 2023-10-06T10:01:53.236
                RunnerLogEvent(
                    timestamp=1696586513237, message=b"Log4"
                ),  # 2023-10-06T10:01:53.237
                RunnerLogEvent(
                    timestamp=1696586513238, message=b"Log5"
                ),  # 2023-10-06T10:01:53.238
            ],
            job_logs=[],
        )

        # Filter logs between 2023-10-06T10:01:53.235 and 2023-10-06T10:01:53.237
        poll_request = PollLogsRequest(
            run_name="test_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            start_time=datetime(2023, 10, 6, 10, 1, 53, 235000, timezone.utc),
            end_time=datetime(2023, 10, 6, 10, 1, 53, 237000, timezone.utc),
            limit=10,
            diagnose=True,
            descending=True,
        )
        job_submission_logs = log_storage.poll_logs(project, poll_request)

        # Should return logs in descending order within the time range
        assert len(job_submission_logs.logs) == 2
        assert job_submission_logs.logs[0].message == "Log4"  # timestamp 237
        assert job_submission_logs.logs[1].message == "Log3"  # timestamp 236
        assert job_submission_logs.next_token is None  # No more logs in range

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_poll_logs_descending_invalid_next_token(
        self, test_db, session: AsyncSession, tmp_path: Path
    ):
        """Test descending log polling with invalid next_token."""
        project = await create_project(session=session)
        log_storage = FileLogStorage(tmp_path)

        # Test with non-integer next_token
        poll_request = PollLogsRequest(
            run_name="test_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            next_token="invalid",
            limit=10,
            diagnose=True,
            descending=True,
        )
        with pytest.raises(ServerClientError):
            log_storage.poll_logs(project, poll_request)

        # Test with negative next_token
        poll_request.next_token = "-1"
        with pytest.raises(ServerClientError):
            log_storage.poll_logs(project, poll_request)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_poll_logs_descending_empty_file(
        self, test_db, session: AsyncSession, tmp_path: Path
    ):
        """Test descending log polling with empty log file."""
        project = await create_project(session=session)
        log_storage = FileLogStorage(tmp_path)

        # Test with non-existent log file
        poll_request = PollLogsRequest(
            run_name="nonexistent_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            limit=10,
            diagnose=True,
            descending=True,
        )
        job_submission_logs = log_storage.poll_logs(project, poll_request)

        # Should return empty logs without error
        assert len(job_submission_logs.logs) == 0
        assert job_submission_logs.next_token is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_poll_logs_descending_pagination_workflow(
        self, test_db, session: AsyncSession, tmp_path: Path
    ):
        """Test complete descending pagination workflow."""
        project = await create_project(session=session)
        log_storage = FileLogStorage(tmp_path)

        # Write test logs
        log_storage.write_logs(
            project=project,
            run_name="test_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            runner_logs=[
                RunnerLogEvent(timestamp=1696586513234, message=b"Log1"),
                RunnerLogEvent(timestamp=1696586513235, message=b"Log2"),
                RunnerLogEvent(timestamp=1696586513236, message=b"Log3"),
                RunnerLogEvent(timestamp=1696586513237, message=b"Log4"),
                RunnerLogEvent(timestamp=1696586513238, message=b"Log5"),
            ],
            job_logs=[],
        )

        # First page: get last 2 logs
        poll_request = PollLogsRequest(
            run_name="test_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            limit=2,
            diagnose=True,
            descending=True,
        )
        job_submission_logs = log_storage.poll_logs(project, poll_request)

        assert len(job_submission_logs.logs) == 2
        assert job_submission_logs.logs[0].message == "Log5"
        assert job_submission_logs.logs[1].message == "Log4"
        assert job_submission_logs.next_token is not None

        # Second page: get next 2 logs
        poll_request.next_token = job_submission_logs.next_token
        job_submission_logs = log_storage.poll_logs(project, poll_request)

        assert len(job_submission_logs.logs) == 2
        assert job_submission_logs.logs[0].message == "Log3"
        assert job_submission_logs.logs[1].message == "Log2"
        assert job_submission_logs.next_token is not None

        # Third page: get remaining log
        poll_request.next_token = job_submission_logs.next_token
        job_submission_logs = log_storage.poll_logs(project, poll_request)

        assert len(job_submission_logs.logs) == 1
        assert job_submission_logs.logs[0].message == "Log1"
        assert job_submission_logs.next_token is None  # No more logs

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_poll_logs_descending_malformed_lines(
        self, test_db, session: AsyncSession, tmp_path: Path
    ):
        """Test descending log polling with malformed log lines."""
        project = await create_project(session=session)
        log_storage = FileLogStorage(tmp_path)

        # Create log file with malformed lines
        log_file_path = log_storage._get_log_file_path(
            project_name=project.name,
            run_name="test_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            producer=LogProducer.RUNNER,
        )
        log_file_path.parent.mkdir(exist_ok=True, parents=True)

        with open(log_file_path, "w") as f:
            f.write(
                '{"timestamp": "2023-10-06T10:01:53.234Z", "log_source": "stdout", "message": "Log1"}\n'
            )
            f.write("invalid json line\n")
            f.write(
                '{"timestamp": "2023-10-06T10:01:53.235Z", "log_source": "stdout", "message": "Log2"}\n'
            )
            f.write("another invalid line\n")
            f.write(
                '{"timestamp": "2023-10-06T10:01:53.236Z", "log_source": "stdout", "message": "Log3"}\n'
            )

        # Test descending polling
        poll_request = PollLogsRequest(
            run_name="test_run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            limit=10,
            diagnose=True,
            descending=True,
        )
        job_submission_logs = log_storage.poll_logs(project, poll_request)

        # Should return only valid logs in descending order, skipping malformed lines
        assert len(job_submission_logs.logs) == 3
        assert job_submission_logs.logs[0].message == "Log3"
        assert job_submission_logs.logs[1].message == "Log2"
        assert job_submission_logs.logs[2].message == "Log1"


class TestCloudWatchLogStorage:
    FAKE_NOW = datetime(2023, 10, 6, 10, 1, 54, tzinfo=timezone.utc)

    @freeze_time(FAKE_NOW)
    @pytest_asyncio.fixture
    async def project(self, test_db, session: AsyncSession) -> ProjectModel:
        project = await create_project(session=session, name="test-proj")
        return project

    @pytest.fixture
    def mock_client(self, monkeypatch: pytest.MonkeyPatch) -> Mock:
        mock = Mock()
        monkeypatch.setattr("boto3.Session.client", Mock(return_value=mock))
        mock.get_log_events.return_value = {
            "events": [],
            "nextBackwardToken": "bwd",
            "nextForwardToken": "fwd",
        }
        return mock

    @pytest.fixture
    def log_storage(self, mock_client: Mock) -> CloudWatchLogStorage:
        return CloudWatchLogStorage(group="test-group")

    @pytest.fixture
    def mock_ensure_stream_exists(self, monkeypatch: pytest.MonkeyPatch) -> Mock:
        mock = Mock()
        monkeypatch.setattr(CloudWatchLogStorage, "_ensure_stream_exists", mock)
        return mock

    @pytest.fixture
    def poll_logs_request(self) -> PollLogsRequest:
        return PollLogsRequest(
            run_name="test-run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            start_time=None,
            end_time=None,
            limit=100,
        )

    def test_init_error_client_instantiation_exception(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "boto3.Session.client", Mock(side_effect=botocore.exceptions.NoRegionError)
        )
        with pytest.raises(LogStorageError, match="NoRegionError"):
            CloudWatchLogStorage(group="test-group")

    def test_init_error_client_request_error(self, mock_client: Mock):
        mock_client.describe_log_streams.side_effect = botocore.exceptions.ClientError({}, "name")
        with pytest.raises(LogStorageError, match="ClientError"):
            CloudWatchLogStorage(group="test-group")

    def test_init_error_group_not_found(self, mock_client: Mock):
        mock_client.describe_log_streams.side_effect = botocore.exceptions.ClientError(
            {"Error": {"Code": "ResourceNotFoundException"}}, "op_name"
        )
        with pytest.raises(LogStorageError, match=r"'test-group' does not exist"):
            CloudWatchLogStorage(group="test-group")

    def test_ensure_stream_exists_new(self, log_storage: CloudWatchLogStorage, mock_client: Mock):
        mock_client.describe_log_streams.reset_mock()
        mock_client.describe_log_streams.return_value = {
            "logStreams": [{"logStreamName": "test-stream-1"}]
        }
        log_storage._ensure_stream_exists("test-stream")

        assert "test-stream" in log_storage._streams
        mock_client.describe_log_streams.assert_called_once_with(
            logGroupName="test-group", logStreamNamePrefix="test-stream"
        )
        mock_client.create_log_stream.assert_called_once_with(
            logGroupName="test-group", logStreamName="test-stream"
        )

    def test_ensure_stream_exists_existing(
        self, log_storage: CloudWatchLogStorage, mock_client: Mock
    ):
        mock_client.describe_log_streams.reset_mock()
        mock_client.describe_log_streams.return_value = {
            "logStreams": [{"logStreamName": "test-stream"}]
        }
        log_storage._ensure_stream_exists("test-stream")

        assert "test-stream" in log_storage._streams
        mock_client.describe_log_streams.assert_called_once_with(
            logGroupName="test-group", logStreamNamePrefix="test-stream"
        )
        mock_client.create_log_stream.assert_not_called()

    def test_ensure_stream_exists_cached(
        self, log_storage: CloudWatchLogStorage, mock_client: Mock
    ):
        mock_client.describe_log_streams.reset_mock()
        log_storage._streams.add("test-stream")
        log_storage._ensure_stream_exists("test-stream")

        mock_client.describe_log_streams.assert_not_called()
        mock_client.create_log_stream.assert_not_called()

    def test_ensure_stream_exists_cached_forced(
        self, log_storage: CloudWatchLogStorage, mock_client: Mock
    ):
        mock_client.describe_log_streams.reset_mock()
        mock_client.describe_log_streams.return_value = {"logStreams": []}
        log_storage._streams.add("test-stream")
        log_storage._ensure_stream_exists("test-stream", force=True)

        assert "test-stream" in log_storage._streams
        mock_client.describe_log_streams.assert_called_once_with(
            logGroupName="test-group", logStreamNamePrefix="test-stream"
        )
        mock_client.create_log_stream.assert_called_once_with(
            logGroupName="test-group", logStreamName="test-stream"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("descending", [False, True])
    async def test_poll_logs_empty_response(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
        descending: bool,
    ):
        # Test with no next token - should not trigger retrying
        mock_client.get_log_events.return_value = {
            "events": [],
            "nextBackwardToken": None,  # No next token
            "nextForwardToken": None,  # No next token
        }
        poll_logs_request.descending = descending
        job_submission_logs = log_storage.poll_logs(project, poll_logs_request)

        assert job_submission_logs.logs == []
        # When no next token is provided initially, retrying doesn't trigger
        assert mock_client.get_log_events.call_count == 1

    @pytest.mark.asyncio
    async def test_poll_logs_descending_empty_response_max_tries(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
    ):
        # Test that we retry up to MAX_RETRIES times when getting empty responses with changing tokens
        # Need to provide exactly 10 responses for MAX_RETRIES
        mock_client.get_log_events.side_effect = [
            {
                "events": [],
                "nextBackwardToken": "bwd1",
                "nextForwardToken": "fwd",
            },
            {
                "events": [],
                "nextBackwardToken": "bwd2",  # Different token
                "nextForwardToken": "fwd",
            },
            {
                "events": [],
                "nextBackwardToken": "bwd3",  # Different token
                "nextForwardToken": "fwd",
            },
            {
                "events": [],
                "nextBackwardToken": "bwd4",  # Different token
                "nextForwardToken": "fwd",
            },
            {
                "events": [],
                "nextBackwardToken": "bwd5",  # Different token
                "nextForwardToken": "fwd",
            },
            {
                "events": [],
                "nextBackwardToken": "bwd6",  # Different token
                "nextForwardToken": "fwd",
            },
            {
                "events": [],
                "nextBackwardToken": "bwd7",  # Different token
                "nextForwardToken": "fwd",
            },
            {
                "events": [],
                "nextBackwardToken": "bwd8",  # Different token
                "nextForwardToken": "fwd",
            },
            {
                "events": [],
                "nextBackwardToken": "bwd9",  # Different token
                "nextForwardToken": "fwd",
            },
            {
                "events": [],
                "nextBackwardToken": "bwd10",  # Different token
                "nextForwardToken": "fwd",
            },
        ]
        poll_logs_request.descending = True
        job_submission_logs = log_storage.poll_logs(project, poll_logs_request)

        assert job_submission_logs.logs == []
        # For descending requests, we return the next token even when no logs found
        assert job_submission_logs.next_token == "bwd10"
        assert mock_client.get_log_events.call_count == 10  # MAX_RETRIES

    @pytest.mark.asyncio
    async def test_poll_logs_ascending_empty_response_max_tries(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
    ):
        # Test that for ascending requests, we return None next_token when no logs found after max retries
        # Need to provide exactly 10 responses for MAX_RETRIES
        mock_client.get_log_events.side_effect = [
            {
                "events": [],
                "nextBackwardToken": "bwd",
                "nextForwardToken": "fwd1",
            },
            {
                "events": [],
                "nextBackwardToken": "bwd",
                "nextForwardToken": "fwd2",  # Different token
            },
            {
                "events": [],
                "nextBackwardToken": "bwd",
                "nextForwardToken": "fwd3",  # Different token
            },
            {
                "events": [],
                "nextBackwardToken": "bwd",
                "nextForwardToken": "fwd4",  # Different token
            },
            {
                "events": [],
                "nextBackwardToken": "bwd",
                "nextForwardToken": "fwd5",  # Different token
            },
            {
                "events": [],
                "nextBackwardToken": "bwd",
                "nextForwardToken": "fwd6",  # Different token
            },
            {
                "events": [],
                "nextBackwardToken": "bwd",
                "nextForwardToken": "fwd7",  # Different token
            },
            {
                "events": [],
                "nextBackwardToken": "bwd",
                "nextForwardToken": "fwd8",  # Different token
            },
            {
                "events": [],
                "nextBackwardToken": "bwd",
                "nextForwardToken": "fwd9",  # Different token
            },
            {
                "events": [],
                "nextBackwardToken": "bwd",
                "nextForwardToken": "fwd10",  # Different token
            },
        ]
        poll_logs_request.descending = False
        job_submission_logs = log_storage.poll_logs(project, poll_logs_request)

        assert job_submission_logs.logs == []
        # For ascending requests, we return None when no logs found after max retries
        assert job_submission_logs.next_token is None
        assert mock_client.get_log_events.call_count == 10  # MAX_RETRIES

    @pytest.mark.asyncio
    async def test_poll_logs_request_params_asc_no_diag_no_dates(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
    ):
        # Ensure response has events to avoid retrying
        mock_client.get_log_events.return_value = {
            "events": [
                {"timestamp": 1696586513234, "message": "Hello"},
            ],
            "nextBackwardToken": "bwd",
            "nextForwardToken": "fwd",
        }
        poll_logs_request.descending = False
        poll_logs_request.limit = 5
        poll_logs_request.diagnose = False
        log_storage.poll_logs(project, poll_logs_request)
        assert mock_client.get_log_events.call_count == 1
        mock_client.get_log_events.assert_called_with(
            logGroupName="test-group",
            logStreamName="test-proj/test-run/1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e/job",
            limit=5,
            startFromHead=True,  # For ascending requests
            endTime=mock_client.get_log_events.call_args.kwargs["endTime"],  # endTime is auto-set
        )

    @pytest.mark.asyncio
    async def test_poll_logs_request_params_desc_diag_with_dates(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
    ):
        # Ensure the response has events to avoid retrying
        mock_client.get_log_events.return_value = {
            "events": [{"timestamp": 1696586513234, "message": "SGVsbG8="}],
            "nextBackwardToken": "bwd",
            "nextForwardToken": "fwd",
        }
        poll_logs_request.start_time = datetime(
            2023, 10, 6, 10, 1, 53, 234000, tzinfo=timezone.utc
        )
        poll_logs_request.end_time = datetime(2023, 10, 7, 10, 1, 53, 234000, tzinfo=timezone.utc)
        poll_logs_request.descending = True
        poll_logs_request.limit = 10
        poll_logs_request.diagnose = True
        log_storage.poll_logs(project, poll_logs_request)
        assert mock_client.get_log_events.call_count == 1
        mock_client.get_log_events.assert_called_with(
            logGroupName="test-group",
            logStreamName="test-proj/test-run/1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e/runner",
            limit=10,
            startFromHead=False,  # For descending requests
            startTime=1696586513234,  # start_time (no +1ms increment)
            endTime=1696672913234,
        )

    @pytest.mark.asyncio
    async def test_poll_logs_exception_resource_not_found(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
    ):
        mock_client.get_log_events.side_effect = botocore.exceptions.ClientError(
            {"Error": {"Code": "ResourceNotFoundException"}}, "op_name"
        )
        job_submission_logs = log_storage.poll_logs(project, poll_logs_request)
        assert job_submission_logs.logs == []

    @pytest.mark.asyncio
    async def test_poll_logs_exception_other(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
    ):
        mock_client.get_log_events.side_effect = botocore.exceptions.ClientError(
            {"Error": {"Code": "SomeError"}}, "op_name"
        )
        with pytest.raises(LogStorageError, match="ClientError"):
            log_storage.poll_logs(project, poll_logs_request)

    @pytest.mark.asyncio
    @freeze_time(FAKE_NOW)
    async def test_write_logs(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        mock_ensure_stream_exists: Mock,
    ):
        log_storage.write_logs(
            project=project,
            run_name="test-run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            runner_logs=[
                RunnerLogEvent(timestamp=1696586513234, message=b"Hello"),
            ],
            job_logs=[
                RunnerLogEvent(timestamp=1696586513235, message=b"World"),
            ],
        )

        expected_runner_stream = "test-proj/test-run/1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e/runner"
        expected_job_stream = "test-proj/test-run/1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e/job"
        expected_ensure_stream_exists_calls = [
            call(expected_runner_stream),
            call(expected_job_stream),
        ]
        expected_put_log_events_calls = [
            call(
                logGroupName="test-group",
                logStreamName=expected_runner_stream,
                logEvents=[
                    {"timestamp": 1696586513234, "message": "Hello"},
                ],
            ),
            call(
                logGroupName="test-group",
                logStreamName=expected_job_stream,
                logEvents=[
                    {"timestamp": 1696586513235, "message": "World"},
                ],
            ),
        ]

        assert mock_ensure_stream_exists.call_count == 2
        mock_ensure_stream_exists.assert_has_calls(
            expected_ensure_stream_exists_calls, any_order=True
        )

        assert mock_client.put_log_events.call_count == 2
        mock_client.put_log_events.assert_has_calls(expected_put_log_events_calls, any_order=True)

    @pytest.mark.asyncio
    @freeze_time(FAKE_NOW)
    async def test_write_logs_resource_not_found(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        mock_ensure_stream_exists: Mock,
    ):
        mock_client.put_log_events.side_effect = [
            # First call ­-- exception
            botocore.exceptions.ClientError(
                {"Error": {"Code": "ResourceNotFoundException"}}, "op_name"
            ),
            # Second call -- OK, stream has been recreated
            None,
        ]
        log_storage.write_logs(
            project=project,
            run_name="test-run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            runner_logs=[
                RunnerLogEvent(timestamp=1696586513234, message=b"Hello"),
            ],
            job_logs=[],
        )
        assert mock_ensure_stream_exists.call_count == 2
        mock_ensure_stream_exists.assert_has_calls(
            [
                call("test-proj/test-run/1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e/runner"),
                call("test-proj/test-run/1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e/runner", force=True),
            ]
        )
        assert mock_client.put_log_events.call_count == 2

    @pytest.mark.asyncio
    @freeze_time(FAKE_NOW)
    async def test_write_logs_other_exception(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        mock_ensure_stream_exists: Mock,
    ):
        mock_ensure_stream_exists.side_effect = botocore.exceptions.ConnectionError(error="err")
        with pytest.raises(LogStorageError, match="ConnectionError"):
            log_storage.write_logs(
                project=project,
                run_name="test-run",
                job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
                runner_logs=[
                    RunnerLogEvent(timestamp=1696586513234, message=b"Hello"),
                ],
                job_logs=[],
            )

    @pytest.mark.asyncio
    @freeze_time(FAKE_NOW)
    async def test_write_logs_not_in_chronological_order(
        self,
        caplog: pytest.LogCaptureFixture,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        mock_ensure_stream_exists: Mock,
    ):
        caplog.set_level(logging.ERROR)
        log_storage.write_logs(
            project=project,
            run_name="test-run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            runner_logs=[
                RunnerLogEvent(timestamp=1696586513235, message=b"1"),
                RunnerLogEvent(timestamp=1696586513237, message=b"3"),
                RunnerLogEvent(timestamp=1696586513237, message=b"4"),
                RunnerLogEvent(timestamp=1696586513236, message=b"2"),
                RunnerLogEvent(timestamp=1696586513237, message=b"5"),
            ],
            job_logs=[],
        )

        mock_client.put_log_events.assert_called_once_with(
            logGroupName="test-group",
            logStreamName="test-proj/test-run/1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e/runner",
            logEvents=[
                {"timestamp": 1696586513235, "message": "1"},
                {"timestamp": 1696586513236, "message": "2"},
                {"timestamp": 1696586513237, "message": "3"},
                {"timestamp": 1696586513237, "message": "4"},
                {"timestamp": 1696586513237, "message": "5"},
            ],
        )
        assert "events are not in chronological order" in caplog.text

    @pytest.mark.asyncio
    @freeze_time(FAKE_NOW)
    async def test_write_logs_past_and_future_events(
        self,
        caplog: pytest.LogCaptureFixture,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        mock_ensure_stream_exists: Mock,
    ):
        def _delta_ms(**kwargs: int) -> int:
            return int(timedelta(**kwargs).total_seconds() * 1000)

        timestamp = int(self.FAKE_NOW.timestamp() * 1000)

        log_storage.write_logs(
            project=project,
            run_name="test-run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            runner_logs=[
                RunnerLogEvent(timestamp=timestamp - _delta_ms(days=14), message=b"skipped"),
                RunnerLogEvent(timestamp=timestamp - _delta_ms(days=13, hours=23), message=b"1"),
                RunnerLogEvent(timestamp=timestamp, message=b"2"),
                RunnerLogEvent(timestamp=timestamp + _delta_ms(minutes=90), message=b"3"),
                RunnerLogEvent(timestamp=timestamp + _delta_ms(minutes=115), message=b"skipped"),
                RunnerLogEvent(timestamp=timestamp + _delta_ms(hours=2), message=b"skipped"),
            ],
            job_logs=[],
        )

        assert "skipping 1 past event(s)" in caplog.text
        assert "skipping 2 future event(s)" in caplog.text
        actual = [
            e["message"]
            for c in mock_client.put_log_events.call_args_list
            for e in c.kwargs["logEvents"]
        ]
        assert actual == ["1", "2", "3"]

    @pytest.mark.parametrize(
        ["messages", "expected"],
        [
            # `messages` is a concatenated list for better readability — each list is a batch
            # `expected` is a list of lists, each nested list is a batch.
            [
                ["", "toolong"],
                [],
            ],
            [
                ["111", "toolong", "111"] + ["222222"] + ["333"],
                [["111", "111"], ["222222"], ["333"]],
            ],
            [
                ["111", "111"] + ["222", "222"],
                [["111", "111"], ["222", "222"]],
            ],
            [
                ["111", "111"] + ["222"],
                [["111", "111"], ["222"]],
            ],
            [
                ["111"] + ["222222"] + ["333", "333"],
                [["111"], ["222222"], ["333", "333"]],
            ],
        ],
    )
    @pytest.mark.asyncio
    @freeze_time(FAKE_NOW)
    async def test_write_logs_batching_by_size(
        self,
        monkeypatch: pytest.MonkeyPatch,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        mock_ensure_stream_exists: Mock,
        messages: List[str],
        expected: List[List[str]],
    ):
        # maximum 6 bytes: 6 (raw bytes) + 26 (overhead) = 32
        monkeypatch.setattr(CloudWatchLogStorage, "MESSAGE_MAX_SIZE", 32)
        monkeypatch.setattr(CloudWatchLogStorage, "BATCH_MAX_SIZE", 60)
        log_storage.write_logs(
            project=project,
            run_name="test-run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            runner_logs=[
                RunnerLogEvent(timestamp=1696586513234, message=message.encode())
                for message in messages
            ],
            job_logs=[],
        )
        assert mock_client.put_log_events.call_count == len(expected)
        actual = [
            [e["message"] for e in c.kwargs["logEvents"]]
            for c in mock_client.put_log_events.call_args_list
        ]
        assert actual == expected

    @pytest.mark.parametrize(
        ["messages", "expected"],
        [
            # `messages` is a concatenated list for better readability — each list is a batch
            # `expected` is a list of lists, each nested list is a batch.
            [
                ["111", "111", "111"] + ["222"],
                [["111", "111", "111"], ["222"]],
            ],
            [
                ["111", "111", "111"] + ["222", "222", "toolongtoolong", "", "222222"],
                [["111", "111", "111"], ["222", "222", "222222"]],
            ],
        ],
    )
    @pytest.mark.asyncio
    @freeze_time(FAKE_NOW)
    async def test_write_logs_batching_by_count(
        self,
        monkeypatch: pytest.MonkeyPatch,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        mock_ensure_stream_exists: Mock,
        messages: List[str],
        expected: List[List[str]],
    ):
        # maximum 6 bytes: 6 (raw bytes) + 26 (overhead) = 32
        monkeypatch.setattr(CloudWatchLogStorage, "MESSAGE_MAX_SIZE", 32)
        monkeypatch.setattr(CloudWatchLogStorage, "EVENT_MAX_COUNT_IN_BATCH", 3)
        log_storage.write_logs(
            project=project,
            run_name="test-run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            runner_logs=[
                RunnerLogEvent(timestamp=1696586513234, message=message.encode())
                for message in messages
            ],
            job_logs=[],
        )
        assert mock_client.put_log_events.call_count == len(expected)
        actual = [
            [e["message"] for e in c.kwargs["logEvents"]]
            for c in mock_client.put_log_events.call_args_list
        ]
        assert actual == expected

    @pytest.mark.asyncio
    @freeze_time(FAKE_NOW)
    async def test_write_logs_batching_by_timestamp(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        mock_ensure_stream_exists: Mock,
    ):
        def _delta_ms(**kwargs: int) -> int:
            return int(timedelta(**kwargs).total_seconds() * 1000)

        timestamp = int(self.FAKE_NOW.timestamp() * 1000) - _delta_ms(days=3)

        log_storage.write_logs(
            project=project,
            run_name="test-run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            runner_logs=[
                # empty message, should be ignored
                RunnerLogEvent(timestamp=timestamp - _delta_ms(days=1), message=b""),
                # first batch
                RunnerLogEvent(timestamp=timestamp, message=b"1"),
                RunnerLogEvent(timestamp=timestamp + _delta_ms(hours=23), message=b"2"),
                RunnerLogEvent(timestamp=timestamp + _delta_ms(hours=24), message=b"3"),
                # second batch
                RunnerLogEvent(timestamp=timestamp + _delta_ms(hours=24, seconds=1), message=b"4"),
                RunnerLogEvent(timestamp=timestamp + _delta_ms(hours=30), message=b"5"),
                RunnerLogEvent(timestamp=timestamp + _delta_ms(hours=48), message=b"6"),
                # third batch
                RunnerLogEvent(timestamp=timestamp + _delta_ms(hours=50), message=b"7"),
            ],
            job_logs=[],
        )

        expected = [["1", "2", "3"], ["4", "5", "6"], ["7"]]
        assert mock_client.put_log_events.call_count == len(expected)
        actual = [
            [e["message"] for e in c.kwargs["logEvents"]]
            for c in mock_client.put_log_events.call_args_list
        ]
        assert actual == expected

    @pytest.mark.asyncio
    async def test_poll_logs_non_empty_response(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
    ):
        mock_client.get_log_events.return_value["events"] = [
            {"timestamp": 1696586513234, "message": "Hello"},
            {"timestamp": 1696586513235, "message": "World"},
        ]
        poll_logs_request.limit = 2
        job_submission_logs = log_storage.poll_logs(project, poll_logs_request)

        assert job_submission_logs.logs == [
            LogEvent(
                timestamp=datetime(2023, 10, 6, 10, 1, 53, 234000, tzinfo=timezone.utc),
                log_source=LogEventSource.STDOUT,
                message="Hello",
            ),
            LogEvent(
                timestamp=datetime(2023, 10, 6, 10, 1, 53, 235000, tzinfo=timezone.utc),
                log_source=LogEventSource.STDOUT,
                message="World",
            ),
        ]

    @pytest.mark.asyncio
    async def test_poll_logs_descending_non_empty_response_on_first_call(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
    ):
        # Ensure response has events to avoid retrying
        mock_client.get_log_events.return_value = {
            "events": [
                {"timestamp": 1696586513234, "message": "Hello"},
                {"timestamp": 1696586513235, "message": "World"},
            ],
            "nextBackwardToken": "bwd456",
            "nextForwardToken": "fwd",
        }
        poll_logs_request.descending = True
        poll_logs_request.limit = 2
        job_submission_logs = log_storage.poll_logs(project, poll_logs_request)

        # Events should be reversed for descending order
        assert job_submission_logs.logs == [
            LogEvent(
                timestamp=datetime(2023, 10, 6, 10, 1, 53, 235000, tzinfo=timezone.utc),
                log_source=LogEventSource.STDOUT,
                message="World",
            ),
            LogEvent(
                timestamp=datetime(2023, 10, 6, 10, 1, 53, 234000, tzinfo=timezone.utc),
                log_source=LogEventSource.STDOUT,
                message="Hello",
            ),
        ]
        # Should return nextBackwardToken for descending requests
        assert job_submission_logs.next_token == "bwd456"
        assert mock_client.get_log_events.call_count == 1

    @pytest.mark.asyncio
    async def test_next_token_ascending_pagination(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
    ):
        """Test next_token behavior for ascending pagination"""
        # Setup response with nextForwardToken
        mock_client.get_log_events.return_value = {
            "events": [
                {"timestamp": 1696586513234, "message": "Hello"},
                {"timestamp": 1696586513235, "message": "World"},
            ],
            "nextBackwardToken": "bwd",
            "nextForwardToken": "fwd123",
        }

        poll_logs_request.descending = False
        poll_logs_request.limit = 2
        result = log_storage.poll_logs(project, poll_logs_request)

        assert len(result.logs) == 2
        assert result.next_token == "fwd123"  # Should return nextForwardToken

        # Verify API was called with correct parameters
        mock_client.get_log_events.assert_called_once_with(
            logGroupName="test-group",
            logStreamName="test-proj/test-run/1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e/job",
            limit=2,
            startFromHead=True,  # For ascending requests
            endTime=mock_client.get_log_events.call_args.kwargs["endTime"],  # endTime is auto-set
        )

    @pytest.mark.asyncio
    async def test_next_token_descending_pagination(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
    ):
        """Test next_token behavior for descending pagination"""
        # Setup response with nextBackwardToken
        mock_client.get_log_events.return_value = {
            "events": [
                {"timestamp": 1696586513234, "message": "Hello"},
                {"timestamp": 1696586513235, "message": "World"},
            ],
            "nextBackwardToken": "bwd456",
            "nextForwardToken": "fwd",
        }

        poll_logs_request.descending = True
        poll_logs_request.limit = 2
        result = log_storage.poll_logs(project, poll_logs_request)

        assert len(result.logs) == 2
        # Events should be reversed for descending order
        assert result.logs[0].message == "World"
        assert result.logs[1].message == "Hello"
        assert result.next_token == "bwd456"  # Should return nextBackwardToken

        # Verify API was called with correct parameters
        mock_client.get_log_events.assert_called_once_with(
            logGroupName="test-group",
            logStreamName="test-proj/test-run/1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e/job",
            limit=2,
            startFromHead=False,  # For descending requests
        )

    @pytest.mark.asyncio
    async def test_next_token_provided_in_request(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
    ):
        """Test that provided next_token is passed to CloudWatch API"""
        mock_client.get_log_events.return_value = {
            "events": [
                {"timestamp": 1696586513234, "message": "Hello"},
            ],
            "nextBackwardToken": "bwd",
            "nextForwardToken": "new_fwd",
        }

        poll_logs_request.next_token = "existing_token_123"
        poll_logs_request.descending = False
        poll_logs_request.limit = 1
        result = log_storage.poll_logs(project, poll_logs_request)

        assert len(result.logs) == 1
        assert result.next_token == "new_fwd"

        # Verify API was called with the provided next_token
        mock_client.get_log_events.assert_called_once_with(
            logGroupName="test-group",
            logStreamName="test-proj/test-run/1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e/job",
            limit=1,
            startFromHead=True,
            nextToken="existing_token_123",
            endTime=mock_client.get_log_events.call_args.kwargs["endTime"],
        )

    @pytest.mark.asyncio
    async def test_next_token_none_when_no_logs(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
    ):
        """Test that next_token is None when no logs are returned"""
        # Test with no next token initially - should not trigger retrying
        mock_client.get_log_events.return_value = {
            "events": [],
            "nextBackwardToken": "bwd",
            "nextForwardToken": "fwd",
        }

        poll_logs_request.limit = 10
        poll_logs_request.descending = False
        result = log_storage.poll_logs(project, poll_logs_request)

        assert len(result.logs) == 0
        assert result.next_token is None  # Should be None when no logs returned

        # Test descending behavior with no next token initially
        poll_logs_request.descending = True
        result = log_storage.poll_logs(project, poll_logs_request)

        assert len(result.logs) == 0
        # For descending requests with no initial next token, we return None
        assert result.next_token is None

    @pytest.mark.asyncio
    async def test_next_token_with_time_filtering(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
    ):
        """Test next_token behavior with time filtering"""
        mock_client.get_log_events.return_value = {
            "events": [
                {"timestamp": 1696586513234, "message": "Hello"},
            ],
            "nextBackwardToken": "bwd_with_time",
            "nextForwardToken": "fwd_with_time",
        }

        poll_logs_request.start_time = datetime(2023, 10, 6, 10, 1, 53, 234000, timezone.utc)
        poll_logs_request.end_time = datetime(2023, 10, 7, 10, 1, 53, 234000, timezone.utc)
        poll_logs_request.next_token = "time_token"
        poll_logs_request.descending = True
        poll_logs_request.diagnose = True
        result = log_storage.poll_logs(project, poll_logs_request)

        assert len(result.logs) == 1
        assert result.next_token == "bwd_with_time"

        # Verify API was called with time filters and next_token
        mock_client.get_log_events.assert_called_once_with(
            logGroupName="test-group",
            logStreamName="test-proj/test-run/1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e/runner",
            limit=100,
            startFromHead=False,
            startTime=1696586513234,  # start_time (no +1ms increment)
            endTime=1696672913234,
            nextToken="time_token",
        )

    @pytest.mark.asyncio
    async def test_next_token_missing_in_cloudwatch_response(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
    ):
        """Test behavior when CloudWatch doesn't return next tokens"""
        mock_client.get_log_events.return_value = {
            "events": [
                {"timestamp": 1696586513234, "message": "Hello"},
            ],
            # No nextBackwardToken or nextForwardToken in response
        }

        poll_logs_request.descending = False
        result = log_storage.poll_logs(project, poll_logs_request)

        assert len(result.logs) == 1
        assert result.next_token is None  # Should be None when no token in response

    @pytest.mark.asyncio
    async def test_next_token_empty_string_in_cloudwatch_response(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
    ):
        """Test behavior when CloudWatch returns empty string tokens"""
        mock_client.get_log_events.return_value = {
            "events": [
                {"timestamp": 1696586513234, "message": "Hello"},
            ],
            "nextBackwardToken": "",
            "nextForwardToken": "",
        }

        poll_logs_request.descending = False
        result = log_storage.poll_logs(project, poll_logs_request)

        assert len(result.logs) == 1
        assert result.next_token == ""  # Should return empty string if that's what AWS returns

    @pytest.mark.asyncio
    async def test_next_token_pagination_workflow(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
    ):
        """Test complete pagination workflow with next_token"""
        # First call - returns some logs with next_token
        mock_client.get_log_events.side_effect = [
            {
                "events": [
                    {"timestamp": 1696586513234, "message": "Hello"},
                    {"timestamp": 1696586513235, "message": "World"},
                ],
                "nextBackwardToken": "bwd",
                "nextForwardToken": "token_page2",
            },
            # Second call - returns final logs with next_token
            {
                "events": [
                    {"timestamp": 1696586513236, "message": "!"},
                ],
                "nextBackwardToken": "final_bwd",
                "nextForwardToken": "final_fwd",
            },
        ]

        # First page
        poll_logs_request.limit = 2
        poll_logs_request.descending = False
        page1 = log_storage.poll_logs(project, poll_logs_request)

        assert len(page1.logs) == 2
        assert page1.logs[0].message == "Hello"
        assert page1.logs[1].message == "World"
        assert page1.next_token == "token_page2"

        # Second page using next_token
        poll_logs_request.next_token = page1.next_token
        page2 = log_storage.poll_logs(project, poll_logs_request)

        assert len(page2.logs) == 1
        assert page2.logs[0].message == "!"
        assert page2.next_token == "final_fwd"

        # Verify both API calls
        assert mock_client.get_log_events.call_count == 2

        # First call should not have nextToken
        first_call = mock_client.get_log_events.call_args_list[0]
        assert "nextToken" not in first_call.kwargs

        # Second call should have nextToken
        second_call = mock_client.get_log_events.call_args_list[1]
        assert second_call.kwargs["nextToken"] == "token_page2"

    @pytest.mark.asyncio
    async def test_poll_logs_retrying_multiple_empty_responses(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
    ):
        """Test retrying behavior when multiple empty responses are returned before finding logs"""
        # First 3 calls return empty, 4th call returns events
        mock_client.get_log_events.side_effect = [
            {
                "events": [],
                "nextBackwardToken": "bwd1",
                "nextForwardToken": "fwd1",
            },
            {
                "events": [],
                "nextBackwardToken": "bwd2",
                "nextForwardToken": "fwd2",
            },
            {
                "events": [],
                "nextBackwardToken": "bwd3",
                "nextForwardToken": "fwd3",
            },
            {
                "events": [
                    {"timestamp": 1696586513234, "message": "Hello"},
                    {"timestamp": 1696586513235, "message": "World"},
                ],
                "nextBackwardToken": "bwd4",
                "nextForwardToken": "fwd4",
            },
        ]

        poll_logs_request.descending = True
        poll_logs_request.limit = 2
        result = log_storage.poll_logs(project, poll_logs_request)

        # Should return events from the 4th call, reversed for descending order
        assert len(result.logs) == 2
        assert result.logs[0].message == "World"
        assert result.logs[1].message == "Hello"
        assert result.next_token == "bwd4"
        assert mock_client.get_log_events.call_count == 4

    @pytest.mark.asyncio
    async def test_poll_logs_retrying_with_changing_tokens(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
    ):
        """Test retrying behavior when tokens change between calls"""
        # Test that we continue retrying as long as tokens change
        mock_client.get_log_events.side_effect = [
            {
                "events": [],
                "nextBackwardToken": "bwd1",
                "nextForwardToken": "fwd1",
            },
            {
                "events": [],
                "nextBackwardToken": "bwd2",  # Different token
                "nextForwardToken": "fwd2",
            },
            {
                "events": [
                    {"timestamp": 1696586513234, "message": "Found"},
                ],
                "nextBackwardToken": "bwd3",
                "nextForwardToken": "fwd3",
            },
        ]

        poll_logs_request.descending = True
        poll_logs_request.limit = 1
        result = log_storage.poll_logs(project, poll_logs_request)

        assert len(result.logs) == 1
        assert result.logs[0].message == "Found"
        assert result.next_token == "bwd3"
        assert mock_client.get_log_events.call_count == 3

    @pytest.mark.asyncio
    async def test_poll_logs_descending_some_responses_are_empty(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
    ):
        # Test retrying logic: first call returns empty, second call returns events
        mock_client.get_log_events.side_effect = [
            {
                "events": [],
                "nextBackwardToken": "bwd1",
                "nextForwardToken": "fwd",
            },
            {
                "events": [
                    {"timestamp": 1696586513234, "message": "SGVsbG8="},
                    {"timestamp": 1696586513235, "message": "V29ybGQ="},
                ],
                "nextBackwardToken": "bwd3",
                "nextForwardToken": "fwd",
            },
        ]
        poll_logs_request.descending = True
        poll_logs_request.limit = 3
        job_submission_logs = log_storage.poll_logs(project, poll_logs_request)

        # Should return events from second call, reversed for descending order
        assert job_submission_logs.logs == [
            LogEvent(
                timestamp=datetime(2023, 10, 6, 10, 1, 53, 235000, tzinfo=timezone.utc),
                log_source=LogEventSource.STDOUT,
                message="V29ybGQ=",
            ),
            LogEvent(
                timestamp=datetime(2023, 10, 6, 10, 1, 53, 234000, tzinfo=timezone.utc),
                log_source=LogEventSource.STDOUT,
                message="SGVsbG8=",
            ),
        ]
        assert job_submission_logs.next_token == "bwd3"
        assert mock_client.get_log_events.call_count == 2

    @pytest.mark.asyncio
    async def test_poll_logs_descending_empty_response_with_same_token(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
    ):
        # Test that when next token doesn't change, we stop retrying
        mock_client.get_log_events.return_value = {
            "events": [],
            "nextBackwardToken": "bwd",
            "nextForwardToken": "fwd",
        }
        poll_logs_request.descending = True
        poll_logs_request.next_token = "bwd"  # Same as returned token
        job_submission_logs = log_storage.poll_logs(project, poll_logs_request)

        assert job_submission_logs.logs == []
        assert job_submission_logs.next_token is None
        assert mock_client.get_log_events.call_count == 1


class TestFileLogStorageReadLinesReversed:
    # No changes to the first 6 tests, they will now pass.
    def test_basic_file(self, tmp_path: Path):
        file = tmp_path / "test.txt"
        content = b"line1\nline2\nline3\n"
        file.write_bytes(content)
        lines = list(FileLogStorage._read_lines_reversed(file))
        assert lines == [
            (b"", 18),
            (b"line3", 12),
            (b"line2", 6),
            (b"line1", 0),
        ]

    def test_file_without_trailing_newline(self, tmp_path: Path):
        file = tmp_path / "test.txt"
        content = b"line1\nline2"
        file.write_bytes(content)
        lines = list(FileLogStorage._read_lines_reversed(file))
        assert lines == [
            (b"line2", 6),
            (b"line1", 0),
        ]

    def test_empty_file(self, tmp_path: Path):
        file = tmp_path / "test.txt"
        file.touch()
        lines = list(FileLogStorage._read_lines_reversed(file))
        assert lines == []

    def test_single_line_file(self, tmp_path: Path):
        file = tmp_path / "test.txt"
        content = b"the only line"
        file.write_bytes(content)
        lines = list(FileLogStorage._read_lines_reversed(file))
        assert lines == [(b"the only line", 0)]

    def test_file_with_empty_lines(self, tmp_path: Path):
        file = tmp_path / "test.txt"
        content = b"lineA\n\nlineC\n"
        file.write_bytes(content)
        lines = list(FileLogStorage._read_lines_reversed(file))
        assert lines == [
            (b"", 13),
            (b"lineC", 7),
            (b"", 6),
            (b"lineA", 0),
        ]

    def test_file_with_only_newlines(self, tmp_path: Path):
        file = tmp_path / "test.txt"
        content = b"\n\n"
        file.write_bytes(content)
        lines = list(FileLogStorage._read_lines_reversed(file))
        assert lines == [
            (b"", 2),
            (b"", 1),
        ]

    def test_large_file_spanning_multiple_chunks(self, tmp_path: Path):
        file = tmp_path / "large_file.txt"
        line_content = b"abcdefghi"  # 9 bytes + 1 newline = 10 bytes per line
        num_lines = 5
        content = b"\n".join([line_content] * num_lines)
        file.write_bytes(content)
        # Pass the small chunk_size directly to the method
        lines = list(FileLogStorage._read_lines_reversed(file, chunk_size=10))
        assert len(lines) == num_lines
        assert lines[0] == (line_content, 40)
        assert lines[1] == (line_content, 30)
        assert lines[2] == (line_content, 20)
        assert lines[3] == (line_content, 10)
        assert lines[4] == (line_content, 0)

    # The rest of the tests will now pass without modification
    def test_start_offset_in_middle_of_line(self, tmp_path: Path):
        file = tmp_path / "test.txt"
        content = b"line1\nline2\nline3\n"
        file.write_bytes(content)
        lines = list(FileLogStorage._read_lines_reversed(file, start_offset=10))
        assert lines == [
            (b"line2", 6),
            (b"line1", 0),
        ]

    def test_start_offset_at_line_boundary(self, tmp_path: Path):
        file = tmp_path / "test.txt"
        content = b"line1\nline2\nline3\n"
        file.write_bytes(content)
        lines = list(FileLogStorage._read_lines_reversed(file, start_offset=12))
        assert lines == [
            (b"line2", 6),
            (b"line1", 0),
        ]

    def test_start_offset_zero(self, tmp_path: Path):
        file = tmp_path / "test.txt"
        content = b"line1\nline2\nline3\n"
        file.write_bytes(content)
        lines = list(FileLogStorage._read_lines_reversed(file, start_offset=0))
        assert lines == []

    def test_start_offset_larger_than_file(self, tmp_path: Path):
        file = tmp_path / "test.txt"
        content = b"line1\nline2\n"
        file.write_bytes(content)
        lines_with_offset = list(FileLogStorage._read_lines_reversed(file, start_offset=1000))
        lines_without_offset = list(FileLogStorage._read_lines_reversed(file))
        assert lines_with_offset == lines_without_offset
        assert lines_with_offset == [(b"", 12), (b"line2", 6), (b"line1", 0)]

    def test_long_line_larger_than_chunk(self, tmp_path: Path):
        file = tmp_path / "long_line.txt"
        content = b"a" * 25
        file.write_bytes(content)
        # Pass the small chunk_size directly
        lines = list(FileLogStorage._read_lines_reversed(file, chunk_size=10))
        assert lines == [(content, 0)]
