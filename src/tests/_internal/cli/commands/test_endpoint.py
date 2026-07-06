import argparse
import base64
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from dstack._internal.cli.commands.endpoint import EndpointCommand
from dstack._internal.core.models.endpoints import Endpoint, EndpointConfiguration, EndpointStatus
from dstack._internal.core.models.logs import JobSubmissionLogs, LogEvent, LogEventSource


def _get_endpoint(status: EndpointStatus = EndpointStatus.RUNNING) -> Endpoint:
    return Endpoint(
        id=uuid4(),
        name="qwen-endpoint",
        project_name="main",
        user="test-user",
        configuration=EndpointConfiguration(name="qwen-endpoint", model="Qwen/Qwen3-0.6B"),
        created_at=datetime.now(timezone.utc),
        last_processed_at=datetime.now(timezone.utc),
        status=status,
        run_name="qwen-endpoint-1",
    )


class _FakeEndpoints:
    def __init__(self, endpoint: Endpoint):
        self._endpoint = endpoint
        self.get_requests = []
        self.stopped_names = []

    def get(self, project_name, name):
        self.get_requests.append(
            {
                "project_name": project_name,
                "name": name,
            }
        )
        return self._endpoint

    def stop(self, project_name, names):
        self.stopped_names.extend(names)


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


def _get_command(endpoint: Endpoint) -> EndpointCommand:
    command = EndpointCommand.__new__(EndpointCommand)
    command.api = SimpleNamespace(
        project="main",
        client=SimpleNamespace(
            endpoints=_FakeEndpoints(endpoint),
            logs=_FakeLogs(),
        ),
    )
    return command


class TestEndpointCommand:
    def test_reads_endpoint_logs(self):
        endpoint = _get_endpoint()
        command = _get_command(endpoint)

        logs = list(command._get_endpoint_logs(endpoint=endpoint, start_time=None))

        assert logs == [b"agent log\n"]
        request = command.api.client.logs.requests[0]
        assert request.run_name == endpoint.name
        assert request.job_submission_id == endpoint.id

    def test_stop_endpoint(self):
        endpoint = _get_endpoint()
        command = _get_command(endpoint)

        command._stop(argparse.Namespace(name=endpoint.name, yes=True))

        assert command.api.client.endpoints.stopped_names == [endpoint.name]

    def test_stop_already_stopped_endpoint_is_noop(self):
        endpoint = _get_endpoint(status=EndpointStatus.STOPPED)
        command = _get_command(endpoint)

        command._stop(argparse.Namespace(name=endpoint.name, yes=True))

        assert command.api.client.endpoints.stopped_names == []

    def test_stop_failed_endpoint_is_noop(self):
        endpoint = _get_endpoint(status=EndpointStatus.FAILED)
        command = _get_command(endpoint)

        command._stop(argparse.Namespace(name=endpoint.name, yes=True))

        assert command.api.client.endpoints.stopped_names == []
