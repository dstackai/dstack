import pytest

from dstack._internal.cli.services.presets.tail import FileLineReader
from dstack._internal.utils import power


@pytest.fixture(autouse=True)
def no_tail_poll_wait(monkeypatch: pytest.MonkeyPatch):
    """
    Stops the tailers from waiting between reads.

    The agent writes its output to files rather than pipes, so reading it means polling,
    and `_POLL_SECONDS` makes every run wait once after the agent has already exited.
    Tests write the whole output up front, so there is nothing to wait for.
    """
    monkeypatch.setattr(FileLineReader, "_POLL_SECONDS", 0)


@pytest.fixture(autouse=True)
def no_idle_sleep_inhibitor(monkeypatch: pytest.MonkeyPatch):
    """Keeps creation tests from spawning the real `caffeinate` helper."""
    monkeypatch.setattr(power, "_start_macos_inhibitor", lambda: None)
