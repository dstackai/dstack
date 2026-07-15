from contextlib import contextmanager
from typing import TYPE_CHECKING, Generator

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncEngine

try:
    from opentelemetry import context as otel_context
    from opentelemetry import metrics as otel_metrics
    from opentelemetry import trace as otel_trace
except ImportError:
    otel_context = None  # type: ignore[assignment]
    otel_metrics = None  # type: ignore[assignment]
    otel_trace = None  # type: ignore[assignment]

_SCOPE_NAME = "dstack.server"

if otel_metrics is not None:
    _task_runs_counter = otel_metrics.get_meter(_SCOPE_NAME).create_counter(
        "dstack.server.background.task.runs",
        unit="{run}",
        description="The number of background task runs",
    )
else:
    _task_runs_counter = None


def configure(app: "FastAPI", engine: "AsyncEngine") -> None:
    """Sets up the OTel signals enabled by the `DSTACK_OTEL_*_ENABLED` env vars."""
    try:
        from dstack._internal.server.utils.otel import utils
    except ImportError as e:
        raise RuntimeError(
            "DSTACK_OTEL_*_ENABLED is set but OpenTelemetry packages are not installed."
            " Install them with `pip install 'dstack[otel]'`."
        ) from e
    utils.configure(app, engine)


@contextmanager
def task_span(name: str) -> Generator[None, None, None]:
    """No-op if OpenTelemetry is not installed or tracing is not configured."""
    if otel_trace is None or otel_context is None:
        yield
        return
    tracer = otel_trace.get_tracer(_SCOPE_NAME)
    with tracer.start_as_current_span(name, context=otel_context.Context()):
        yield


def record_task_run(name: str, *, error: bool) -> None:
    """No-op if OpenTelemetry is not installed or metrics are not configured."""
    if _task_runs_counter is None:
        return
    _task_runs_counter.add(1, {"task": name, "status": "error" if error else "success"})
