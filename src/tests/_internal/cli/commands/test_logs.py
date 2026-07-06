import argparse
from types import SimpleNamespace

import pytest

from dstack._internal.cli.commands.logs import LogsCommand
from dstack._internal.core.errors import CLIError


class _FakeRun:
    def logs(self, **kwargs):
        yield b"run log\n"


class _FakeRuns:
    def __init__(self, run=None):
        self._run = run
        self.requested_names = []

    def get(self, name):
        self.requested_names.append(name)
        return self._run


def _get_command(run=None) -> LogsCommand:
    command = LogsCommand.__new__(LogsCommand)
    command.api = SimpleNamespace(
        runs=_FakeRuns(run=run),
    )
    return command


def _get_args(name="qwen-run"):
    return argparse.Namespace(
        run_name=name,
        diagnose=False,
        replica=0,
        job=0,
    )


class TestLogsCommand:
    def test_reads_run_logs(self):
        command = _get_command(run=_FakeRun())

        logs = list(command._get_logs(args=_get_args(), start_time=None))

        assert logs == [b"run log\n"]
        assert command.api.runs.requested_names == ["qwen-run"]

    def test_errors_when_run_is_not_found(self):
        command = _get_command(run=None)

        with pytest.raises(CLIError, match="Run qwen-run not found"):
            list(command._get_logs(args=_get_args(), start_time=None))
