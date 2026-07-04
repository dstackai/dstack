import argparse
import base64
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from dstack._internal.cli.commands.logs import LogsCommand
from dstack._internal.core.errors import ResourceNotExistsError
from dstack._internal.core.models.endpoints import Endpoint, EndpointConfiguration, EndpointStatus
from dstack._internal.core.models.logs import JobSubmissionLogs, LogEvent, LogEventSource


def _get_endpoint(run_name: str | None = None) -> Endpoint:
    return Endpoint(
        id=uuid4(),
        name="qwen-endpoint",
        project_name="main",
        user="test-user",
        configuration=EndpointConfiguration(name="qwen-endpoint", model="Qwen/Qwen3-0.6B"),
        created_at=datetime.now(timezone.utc),
        last_processed_at=datetime.now(timezone.utc),
        status=EndpointStatus.PROVISIONING,
        deleted=False,
        run_name=run_name,
    )


class _FakeRun:
    def logs(self, **kwargs):
        yield b"service log\n"


class _FakeRuns:
    def __init__(self, run=None):
        self._run = run
        self.requested_names = []

    def get(self, name):
        self.requested_names.append(name)
        return self._run


class _FakeEndpoints:
    def __init__(self, endpoint):
        self._endpoint = endpoint

    def get(self, project_name, name):
        if self._endpoint is None:
            raise ResourceNotExistsError()
        return self._endpoint


class _FakeLogs:
    def __init__(self):
        self.requests = []

    def poll(self, project_name, body):
        self.requests.append(body)
        return JobSubmissionLogs(
            logs=[
                LogEvent(
                    timestamp=datetime.now(timezone.utc),
                    log_source=LogEventSource.STDOUT,
                    message=base64.b64encode(b"agent log\n").decode(),
                )
            ],
        )


def _get_command(endpoint=None, run=None) -> LogsCommand:
    command = LogsCommand.__new__(LogsCommand)
    command.api = SimpleNamespace(
        project="main",
        runs=_FakeRuns(run=run),
        client=SimpleNamespace(
            endpoints=_FakeEndpoints(endpoint=endpoint),
            logs=_FakeLogs(),
        ),
    )
    return command


def _get_args(name="qwen-endpoint"):
    return argparse.Namespace(
        run_name=name,
        diagnose=False,
        replica=0,
        job=0,
    )


class TestLogsCommand:
    def test_reads_endpoint_agent_logs_when_backing_run_is_not_known(self):
        endpoint = _get_endpoint()
        command = _get_command(endpoint=endpoint)

        logs = list(
            command._get_endpoint_logs(endpoint=endpoint, args=_get_args(), start_time=None)
        )

        assert logs == [b"agent log\n"]
        request = command.api.client.logs.requests[0]
        assert request.run_name == endpoint.name
        assert request.job_submission_id == endpoint.id

    def test_reads_backing_service_logs_when_endpoint_has_run(self):
        endpoint = _get_endpoint(run_name="qwen-service")
        command = _get_command(endpoint=endpoint, run=_FakeRun())

        logs = list(
            command._get_endpoint_logs(endpoint=endpoint, args=_get_args(), start_time=None)
        )

        assert logs == [b"service log\n"]
        assert command.api.runs.requested_names == ["qwen-service"]

    def test_endpoint_name_takes_precedence_over_same_name_run(self):
        endpoint = _get_endpoint()
        command = _get_command(endpoint=endpoint, run=_FakeRun())

        logs = list(command._get_logs(args=_get_args(), start_time=None))

        assert logs == [b"agent log\n"]
        assert command.api.runs.requested_names == []
