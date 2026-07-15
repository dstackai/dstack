from contextlib import contextmanager
from typing import TYPE_CHECKING, Generator

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncEngine

try:
    from opentelemetry import context as otel_context
    from opentelemetry import trace as otel_trace
except ImportError:
    otel_context = None  # type: ignore[assignment]
    otel_trace = None  # type: ignore[assignment]

_TRACER_NAME = "dstack.server"


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
    tracer = otel_trace.get_tracer(_TRACER_NAME)
    with tracer.start_as_current_span(name, context=otel_context.Context()):
        yield
