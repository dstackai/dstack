import os
import subprocess

import pytest

from dstack._internal.utils import power
from dstack._internal.utils.power import prevent_idle_sleep

pytestmark = pytest.mark.windows


class _FakeProcess:
    """Stands in for the spawned `caffeinate`, so no test spawns a real one."""

    def __init__(self, *, returncode=None, ignores_terminate: bool = False) -> None:
        self.returncode = returncode
        self.ignores_terminate = ignores_terminate
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        if not self.ignores_terminate:
            self.returncode = -15

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        if self.returncode is None:
            raise subprocess.TimeoutExpired(cmd="caffeinate", timeout=timeout)
        return self.returncode


@pytest.fixture
def macos(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(power, "IS_MACOS", True)


class TestPreventIdleSleep:
    def test_holds_a_caffeinate_assertion_for_the_block(self, monkeypatch, macos):
        commands = []
        process = _FakeProcess()

        def popen(command, **kwargs):
            commands.append(command)
            return process

        monkeypatch.setattr(subprocess, "Popen", popen)

        with prevent_idle_sleep() as prevented:
            assert prevented
            assert not process.terminated

        # `-w` makes the helper exit on its own if this process dies without
        # releasing the assertion.
        assert commands == [["/usr/bin/caffeinate", "-i", "-w", str(os.getpid())]]
        assert process.terminated

    def test_releases_on_exception(self, monkeypatch, macos):
        process = _FakeProcess()
        monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process)

        with pytest.raises(RuntimeError, match="creation failed"):
            with prevent_idle_sleep():
                raise RuntimeError("creation failed")

        assert process.terminated

    def test_kills_a_helper_that_ignores_terminate(self, monkeypatch, macos):
        process = _FakeProcess(ignores_terminate=True)
        monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process)

        with prevent_idle_sleep():
            pass

        assert process.terminated
        assert process.killed

    def test_does_not_signal_an_already_exited_helper(self, monkeypatch, macos):
        process = _FakeProcess(returncode=0)
        monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process)

        with prevent_idle_sleep():
            pass

        assert not process.terminated
        assert not process.killed

    def test_missing_binary_is_a_no_op(self, monkeypatch, macos):
        def popen(command, **kwargs):
            raise FileNotFoundError(command[0])

        monkeypatch.setattr(subprocess, "Popen", popen)

        with prevent_idle_sleep() as prevented:
            assert not prevented

    def test_no_op_on_other_platforms(self, monkeypatch):
        monkeypatch.setattr(power, "IS_MACOS", False)
        monkeypatch.setattr(
            subprocess,
            "Popen",
            lambda *args, **kwargs: pytest.fail("no inhibitor is implemented off macOS"),
        )

        with prevent_idle_sleep() as prevented:
            assert not prevented
