import base64
import itertools
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

from dstack._internal.core.models.logs import LogEvent, LogEventSource
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
            '{"timestamp": "2023-10-06T10:01:53.234000+00:00", "log_source": "stdout", "message": "SGVsbG8="}\n'
            '{"timestamp": "2023-10-06T10:01:53.235000+00:00", "log_source": "stdout", "message": "V29ybGQ="}\n'
        )


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
        poll_logs_request.limit = 2
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
    @pytest.mark.parametrize("descending", [False, True])
    async def test_poll_logs_empty_response(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
        descending: bool,
    ):
        mock_client.get_log_events.return_value["events"] = []
        poll_logs_request.descending = descending
        job_submission_logs = log_storage.poll_logs(project, poll_logs_request)

        assert job_submission_logs.logs == []
        assert mock_client.get_log_events.call_count == 2

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
        poll_logs_request.limit = 2
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
    async def test_poll_logs_descending_some_responses_are_empty(
        self,
        project: ProjectModel,
        log_storage: CloudWatchLogStorage,
        mock_client: Mock,
        poll_logs_request: PollLogsRequest,
    ):
        # The first two calls return empty event lists, though the token is not the same, meaning
        # there are more events, see: https://github.com/dstackai/dstack/issues/1647
        # As the third call returns less events than requested (2 < 3), we continue to poll until
        # accumulate enough events (2 + 2) and return exactly the requested number of events (3),
        # see: https://github.com/dstackai/dstack/issues/2500
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
            {
                "events": [],
                "nextBackwardToken": "bwd4",
                "nextForwardToken": "fwd",
            },
            {
                "events": [
                    {"timestamp": 1696586513232, "message": "aW5pdCAx"},
                    {"timestamp": 1696586513233, "message": "aW5pdCAy"},
                ],
                "nextBackwardToken": "bwd5",
                "nextForwardToken": "fwd",
            },
        ]
        poll_logs_request.descending = True
        poll_logs_request.limit = 3
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
            LogEvent(
                timestamp=datetime(2023, 10, 6, 10, 1, 53, 233000, tzinfo=timezone.utc),
                log_source=LogEventSource.STDOUT,
                message="aW5pdCAy",
            ),
        ]
        assert mock_client.get_log_events.call_count == 5

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
        assert mock_client.get_log_events.call_count == 10

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
        assert mock_client.get_log_events.call_count == 2
        mock_client.get_log_events.assert_called_with(
            logGroupName="test-group",
            logStreamName="test-proj/test-run/1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e/job",
            limit=5,
            startFromHead=True,
            nextToken="fwd",
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
        assert mock_client.get_log_events.call_count == 2
        mock_client.get_log_events.assert_called_with(
            logGroupName="test-group",
            logStreamName="test-proj/test-run/1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e/runner",
            limit=10,
            startFromHead=False,
            startTime=1696586513235,
            endTime=1696672913234,
            nextToken="bwd",
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
                {"timestamp": 1696586513235, "message": "MQ=="},
                {"timestamp": 1696586513236, "message": "Mg=="},
                {"timestamp": 1696586513237, "message": "Mw=="},
                {"timestamp": 1696586513237, "message": "NA=="},
                {"timestamp": 1696586513237, "message": "NQ=="},
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
            base64.b64decode(e["message"]).decode()
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
        # maximum 6 bytes: 12 (in base64) + 26 (overhead) = 34
        monkeypatch.setattr(CloudWatchLogStorage, "MESSAGE_MAX_SIZE", 34)
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
            [base64.b64decode(e["message"]).decode() for e in c.kwargs["logEvents"]]
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
                ["111", "111", "111"] + ["222", "222", "toolong", "", "222222"],
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
        # maximum 6 bytes: 12 (in base64) + 26 (overhead) = 34
        monkeypatch.setattr(CloudWatchLogStorage, "MESSAGE_MAX_SIZE", 34)
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
            [base64.b64decode(e["message"]).decode() for e in c.kwargs["logEvents"]]
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
            [base64.b64decode(e["message"]).decode() for e in c.kwargs["logEvents"]]
            for c in mock_client.put_log_events.call_args_list
        ]
        assert actual == expected
