import logging
from datetime import datetime, timedelta, timezone
from typing import List
from unittest.mock import Mock, call
from uuid import UUID

import botocore.exceptions
import pytest
import pytest_asyncio
import time_machine
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.logs import LogEvent, LogEventSource
from dstack._internal.server.models import ProjectModel
from dstack._internal.server.schemas.logs import PollLogsRequest
from dstack._internal.server.schemas.runner import LogEvent as RunnerLogEvent
from dstack._internal.server.services.logs.aws import (
    CloudWatchLogStorage,
)
from dstack._internal.server.services.logs.base import LogStorageError
from dstack._internal.server.testing.common import create_project


class TestCloudWatchLogStorage:
    FAKE_NOW = datetime(2023, 10, 6, 10, 1, 54, tzinfo=timezone.utc)

    @pytest_asyncio.fixture
    @time_machine.travel(FAKE_NOW, tick=False)
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
    @time_machine.travel(FAKE_NOW, tick=False)
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
    @time_machine.travel(FAKE_NOW, tick=False)
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
    @time_machine.travel(FAKE_NOW, tick=False)
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
    @time_machine.travel(FAKE_NOW, tick=False)
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
    @time_machine.travel(FAKE_NOW, tick=False)
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
    @time_machine.travel(FAKE_NOW, tick=False)
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
    @time_machine.travel(FAKE_NOW, tick=False)
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
    @time_machine.travel(FAKE_NOW, tick=False)
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
