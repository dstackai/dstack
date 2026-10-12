"""
Process-wide setup that must run before the server modules are imported.

Keep this module free of imports that could pull in the libraries it configures.
"""

import os
import sys

from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

_is_process_set_up = False


def set_up_process() -> None:
    """
    Configures process-wide settings that must be applied before dstack server modules,
    and the libraries they use, are imported. Server entry points, including those of
    applications extending the server, must call it before importing anything else from dstack.
    """
    global _is_process_set_up
    _set_grpc_defaults()
    _is_process_set_up = True


def is_process_set_up() -> bool:
    return _is_process_set_up


def _set_grpc_defaults() -> None:
    # gRPC's fork handlers restart its threads in every forked child, which can crash the
    # child before it execs and stall the parent while it waits for the exec. The server
    # forks only to exec subprocesses, so it doesn't need them. gRPC reads this on import.
    if "grpc" in sys.modules and "GRPC_ENABLE_FORK_SUPPORT" not in os.environ:
        logger.warning(
            "grpc was imported before bootstrap.set_up_process(), so gRPC fork support stays"
            " enabled. This may crash subprocesses the server starts and stall the server while"
            " it waits for them. Call set_up_process() before other imports or set"
            " GRPC_ENABLE_FORK_SUPPORT=false in the environment."
        )
    os.environ.setdefault("GRPC_ENABLE_FORK_SUPPORT", "false")
    # Keeps gRPC's own log messages out of server logs. Users can still change this.
    os.environ.setdefault("GRPC_VERBOSITY", "ERROR")
