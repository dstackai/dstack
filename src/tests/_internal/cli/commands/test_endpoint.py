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
    def __init__(self, responses=None):
        self._responses = responses
        self.requests = []

    def poll(self, project_name, body):
        self.requests.append(body)
        if self._responses is not None:
            return self._responses.pop(0)
        return JobSubmissionLogs(
            logs=[
                LogEvent(
                    timestamp=datetime.now(timezone.utc),
                    log_source=LogEventSource.STDOUT,
                    message=base64.b64encode(b"agent log\n").decode(),
                )
            ],
        )


def _get_command(endpoint: Endpoint, logs=None) -> EndpointCommand:
    command = EndpointCommand.__new__(EndpointCommand)
    command.api = SimpleNamespace(
        project="main",
        client=SimpleNamespace(
            endpoints=_FakeEndpoints(endpoint),
            logs=logs or _FakeLogs(),
        ),
    )
    return command


class TestEndpointCommand:
    def test_preset_list_verbose_can_be_before_or_after_list_action(self):
        parser = argparse.ArgumentParser()
        EndpointCommand(parser)._register()

        assert parser.parse_args(["preset", "-v", "list"]).verbose is True
        assert parser.parse_args(["preset", "list", "-v"]).verbose is True
        assert parser.parse_args(["preset", "list"]).verbose is False

    def test_reads_endpoint_logs(self):
        endpoint = _get_endpoint()
        command = _get_command(endpoint)

        logs = list(command._get_endpoint_logs(endpoint=endpoint, start_time=None))

        assert len(logs) == 1
        assert logs[0].startswith(b"[")
        assert logs[0].endswith(b"] agent log\n")
        request = command.api.client.logs.requests[0]
        assert request.run_name == endpoint.name
        assert request.job_submission_id == endpoint.id

    def test_watch_endpoint_logs_does_not_swallow_same_timestamp_logs(self, monkeypatch):
        endpoint = _get_endpoint()
        timestamp = datetime.now(timezone.utc)
        logs_api = _FakeLogs(
            responses=[
                JobSubmissionLogs(
                    logs=[
                        LogEvent(
                            timestamp=timestamp,
                            log_source=LogEventSource.STDOUT,
                            message=base64.b64encode(b"first\n").decode(),
                        ),
                    ],
                ),
                JobSubmissionLogs(
                    logs=[
                        LogEvent(
                            timestamp=timestamp,
                            log_source=LogEventSource.STDOUT,
                            message=base64.b64encode(b"first\n").decode(),
                        ),
                        LogEvent(
                            timestamp=timestamp,
                            log_source=LogEventSource.STDOUT,
                            message=base64.b64encode(b"second\n").decode(),
                        ),
                    ],
                ),
            ],
        )
        command = _get_command(endpoint, logs=logs_api)
        monkeypatch.setattr("dstack._internal.cli.commands.endpoint.time.sleep", lambda _: None)

        logs = command._get_endpoint_logs(endpoint=endpoint, start_time=None, watch=True)

        assert next(logs).endswith(b"] first\n")
        assert next(logs).endswith(b"] second\n")

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
