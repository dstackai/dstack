import itertools
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, call
from uuid import UUID

import botocore.exceptions
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.logs import LogEvent, LogEventSource
from dstack._internal.server.models import ProjectModel
from dstack._internal.server.schemas.logs import PollLogsRequest
from dstack._internal.server.schemas.runner import LogEvent as RunnerLogEvent
from dstack._internal.server.services.logs import (
    CloudWatchLogStorage,
    FileLogStorage,
    LogStorageError,
)
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
            '{"timestamp": "2023-10-06T10:01:53.234000+00:00", "log_source": "stdout", "message": "SGVsbG8="}\n'
            '{"timestamp": "2023-10-06T10:01:53.235000+00:00", "log_source": "stdout", "message": "V29ybGQ="}\n'
        )


class TestCloudWatchLogStorage:
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
            "nextFormartToken": "fwd",
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
    async def test_poll_logs_non_empty_response(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
    ):
        mock_client.get_log_events.return_value["events"] = [
            {"timestamp": 1696586513234, "message": "SGVsbG8="},
            {"timestamp": 1696586513235, "message": "V29ybGQ="},
        ]
        job_submission_logs = log_storage.poll_logs(project, poll_logs_request)

        assert job_submission_logs.logs == [
            LogEvent(
                timestamp=datetime(2023, 10, 6, 10, 1, 53, 234000, tzinfo=timezone.utc),
                log_source=LogEventSource.STDOUT,
                message="SGVsbG8=",
            ),
            LogEvent(
                timestamp=datetime(2023, 10, 6, 10, 1, 53, 235000, tzinfo=timezone.utc),
                log_source=LogEventSource.STDOUT,
                message="V29ybGQ=",
            ),
        ]

    @pytest.mark.asyncio
    async def test_poll_logs_empty_response(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
    ):
        # Check that we don't use the workaround when descending=False -> startFromHead=True
        # https://github.com/dstackai/dstack/issues/1647
        mock_client.get_log_events.return_value["events"] = []
        job_submission_logs = log_storage.poll_logs(project, poll_logs_request)

        assert job_submission_logs.logs == []
        mock_client.get_log_events.assert_called_once()

    @pytest.mark.asyncio
    async def test_poll_logs_descending_non_empty_response_on_first_call(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
    ):
        mock_client.get_log_events.return_value["events"] = [
            {"timestamp": 1696586513234, "message": "SGVsbG8="},
            {"timestamp": 1696586513235, "message": "V29ybGQ="},
        ]
        poll_logs_request.descending = True
        job_submission_logs = log_storage.poll_logs(project, poll_logs_request)

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

    @pytest.mark.asyncio
    async def test_poll_logs_descending_two_first_calls_return_empty_response(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
    ):
        # The first two calls return empty event lists, though the token is not the same, meaning
        # there are more events.
        # https://github.com/dstackai/dstack/issues/1647
        mock_client.get_log_events.side_effect = [
            {
                "events": [],
                "nextBackwardToken": "bwd1",
                "nextForwardToken": "fwd",
            },
            {
                "events": [],
                "nextBackwardToken": "bwd2",
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
        job_submission_logs = log_storage.poll_logs(project, poll_logs_request)

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
        assert mock_client.get_log_events.call_count == 3

    @pytest.mark.asyncio
    async def test_poll_logs_descending_empty_response_with_same_token(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
    ):
        # The first two calls return empty event lists with the same token, meaning we reached
        # the end.
        # https://github.com/dstackai/dstack/issues/1647
        mock_client.get_log_events.side_effect = [
            {
                "events": [],
                "nextBackwardToken": "bwd",
                "nextForwardToken": "fwd",
            },
            {
                "events": [],
                "nextBackwardToken": "bwd",
                "nextForwardToken": "fwd",
            },
            # We should not reach this response
            {
                "events": [
                    {"timestamp": 1696586513234, "message": "SGVsbG8="},
                ],
                "nextBackwardToken": "bwd2",
                "nextForwardToken": "fwd",
            },
        ]
        poll_logs_request.descending = True
        job_submission_logs = log_storage.poll_logs(project, poll_logs_request)

        assert job_submission_logs.logs == []
        assert mock_client.get_log_events.call_count == 2

    @pytest.mark.asyncio
    async def test_poll_logs_descending_empty_response_max_tries(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
    ):
        # Test for a circuit breaker when the API returns empty results on each call, but the
        # token is different on each call.
        # https://github.com/dstackai/dstack/issues/1647
        counter = itertools.count()

        def _response_producer(*args, **kwargs):
            return {
                "events": [],
                "nextBackwardToken": f"bwd{next(counter)}",
                "nextForwardToken": "fwd",
            }

        mock_client.get_log_events.side_effect = _response_producer
        poll_logs_request.descending = True
        job_submission_logs = log_storage.poll_logs(project, poll_logs_request)

        assert job_submission_logs.logs == []
        assert mock_client.get_log_events.call_count == 11  # initial call + 10 tries

    @pytest.mark.asyncio
    async def test_poll_logs_request_params_asc_no_diag_no_dates(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
    ):
        poll_logs_request.descending = False
        poll_logs_request.limit = 5
        poll_logs_request.diagnose = False
        log_storage.poll_logs(project, poll_logs_request)
        mock_client.get_log_events.assert_called_once_with(
            logGroupName="test-group",
            logStreamName="test-proj/test-run/1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e/job",
            limit=5,
            startFromHead=True,
        )

    @pytest.mark.asyncio
    async def test_poll_logs_request_params_desc_diag_with_dates(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
    ):
        # Ensure the first response has events to avoid triggering a workaround for
        # https://github.com/dstackai/dstack/issues/1647
        mock_client.get_log_events.return_value["events"] = [
            {"timestamp": 1696586513234, "message": "SGVsbG8="}
        ]
        poll_logs_request.start_time = datetime(
            2023, 10, 6, 10, 1, 53, 234000, tzinfo=timezone.utc
        )
        poll_logs_request.end_time = datetime(2023, 10, 7, 10, 1, 53, 234000, tzinfo=timezone.utc)
        poll_logs_request.descending = True
        poll_logs_request.limit = 10
        poll_logs_request.diagnose = True
        log_storage.poll_logs(project, poll_logs_request)
        mock_client.get_log_events.assert_called_once_with(
            logGroupName="test-group",
            logStreamName="test-proj/test-run/1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e/runner",
            limit=10,
            startFromHead=False,
            startTime=1696586513235,
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
                    {"timestamp": 1696586513234, "message": "SGVsbG8="},
                ],
            ),
            call(
                logGroupName="test-group",
                logStreamName=expected_job_stream,
                logEvents=[
                    {"timestamp": 1696586513235, "message": "V29ybGQ="},
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
