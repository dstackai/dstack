"""System power management: keeping the machine awake through long foreground work."""

import os
import subprocess
from contextlib import contextmanager
from typing import Iterator, Optional

from dstack._internal.compat import IS_MACOS
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

# Present on every macOS install, so an absolute path avoids a PATH lookup.
_CAFFEINATE_PATH = "/usr/bin/caffeinate"
_STOP_TIMEOUT_SECONDS = 5


@contextmanager
def prevent_idle_sleep() -> Iterator[bool]:
    """Keeps the system from idling into sleep for the duration of the block.

    Yields whether an inhibitor was acquired. Implemented on macOS only; on any
    other platform, and whenever the mechanism is unavailable, this is a no-op
    that yields False, since the caller has to work the same either way.

    Idle sleep only: a machine left open stays awake, while closing a laptop lid
    still puts it to sleep.
    """
    process = _start_macos_inhibitor() if IS_MACOS else None
    try:
        yield process is not None
    finally:
        if process is not None:
            _stop_inhibitor(process)


def _start_macos_inhibitor() -> Optional["subprocess.Popen[bytes]"]:
    # `-i` asserts PreventUserIdleSystemSleep. `-w` makes caffeinate exit on its
    # own once this process is gone, so not even a crash or a SIGKILL can leave
    # the machine awake indefinitely.
    command = [_CAFFEINATE_PATH, "-i", "-w", str(os.getpid())]
    try:
        return subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as e:
        logger.debug("Could not prevent idle sleep: %s", e)
        return None


def _stop_inhibitor(process: "subprocess.Popen[bytes]") -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
        try:
            process.wait(timeout=_STOP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=_STOP_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError) as e:
        # The inhibitor still self-releases once this process exits.
        logger.debug("Could not release the idle sleep inhibitor: %s", e)
