import logging
import re
from typing import Optional, Sequence

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import (
    ParentBased,
    Sampler,
    SamplingResult,
    TraceIdRatioBased,
)
from opentelemetry.trace import Link, SpanKind
from opentelemetry.trace.span import TraceState
from opentelemetry.util.types import Attributes
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine

from dstack._internal import settings as core_settings
from dstack._internal.server import settings
from dstack._internal.server.utils.common import is_background_task_name
from dstack._internal.server.utils.logging import AsyncioCancelledErrorFilter
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


def configure_tracing(app: FastAPI, engine: AsyncEngine) -> None:
    provider = TracerProvider(
        resource=_get_resource(),
        sampler=ParentBased(
            root=_RootSpanNameSampler(
                default_rate=settings.OTEL_TRACES_SAMPLE_RATE,
                background_rate=settings.OTEL_TRACES_BACKGROUND_SAMPLE_RATE,
            )
        ),
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
    _register_db_span_renaming(engine.sync_engine)
    HTTPXClientInstrumentor().instrument()
    RequestsInstrumentor().instrument()
    logger.info("OpenTelemetry tracing enabled")


def configure_log_export() -> None:
    logger_provider = LoggerProvider(resource=_get_resource())
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    set_logger_provider(logger_provider)
    logging.getLogger().addHandler(_build_log_handler(logger_provider))
    logger.info("OpenTelemetry log export enabled")


def _get_resource() -> Resource:
    return Resource.create(
        {
            "service.name": "dstack-server",
            "service.version": core_settings.DSTACK_VERSION or "dev",
            "deployment.environment.name": settings.SERVER_ENVIRONMENT,
        }
    )


def _build_log_handler(logger_provider: LoggerProvider) -> logging.Handler:
    handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
    handler.addFilter(AsyncioCancelledErrorFilter())
    return handler


def _register_db_span_renaming(engine: Engine) -> None:
    """Renames DB spans from `<operation> <db name>` to `<operation> <table>`.

    The default names are not useful for trace lists and span metrics:
    the db name is the same for all spans and is a file path on SQLite.
    Must be called after the engine is instrumented so that the listener
    runs after the instrumentation creates the span.

    NOTE: This hack is needed because SQLAlchemyInstrumentor does not provide any hooks
    to update spans unlike most other instrumentors.
    """

    @event.listens_for(engine, "before_cursor_execute")
    def _rename_db_span(conn, cursor, statement, parameters, context, executemany):
        # The instrumentation stores the still-recording span on the execution context
        span = getattr(context, "_otel_span", None)
        if span is None or not span.is_recording():
            return
        name = _get_db_span_name(statement)
        if name is not None:
            span.update_name(name)


_DB_TABLE_RE = re.compile(r'\b(?:FROM|INTO|UPDATE|JOIN)\s+["\'`]?(\w+)', re.IGNORECASE)


def _get_db_span_name(statement: str) -> Optional[str]:
    operation = statement.split(None, 1)[0].upper() if statement.split() else None
    if operation is None:
        return None
    match = _DB_TABLE_RE.search(statement)
    if match is None:
        return operation
    return f"{operation} {match.group(1)}"


class _RootSpanNameSampler(Sampler):
    """Samples background task traces and other (HTTP) traces at different rates."""

    def __init__(self, default_rate: float, background_rate: float):
        self._default_sampler = TraceIdRatioBased(default_rate)
        self._background_sampler = TraceIdRatioBased(background_rate)

    def should_sample(
        self,
        parent_context: Optional[Context],
        trace_id: int,
        name: str,
        kind: Optional[SpanKind] = None,
        attributes: Attributes = None,
        links: Optional[Sequence[Link]] = None,
        trace_state: Optional[TraceState] = None,
    ) -> SamplingResult:
        sampler = self._default_sampler
        if is_background_task_name(name):
            sampler = self._background_sampler
        return sampler.should_sample(
            parent_context, trace_id, name, kind, attributes, links, trace_state
        )

    def get_description(self) -> str:
        return (
            f"RootSpanNameSampler(default={self._default_sampler.rate},"
            f"background={self._background_sampler.rate})"
        )
