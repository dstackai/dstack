from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.logs import LogProducer
from dstack._internal.server.schemas.logs import PollLogsRequest
from dstack._internal.server.schemas.runner import LogEvent as RunnerLogEvent
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
            '{"timestamp":"2023-10-06T10:01:53.234000Z","log_source":"stdout","message":"Hello"}\n'
            '{"timestamp":"2023-10-06T10:01:53.235000Z","log_source":"stdout","message":"World"}\n'
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
