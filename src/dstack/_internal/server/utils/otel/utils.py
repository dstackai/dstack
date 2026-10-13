import re
from typing import List, Optional

from fastapi import FastAPI
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor
from opentelemetry.sdk.metrics.export import MetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.sampling import ParentBased
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine

from dstack._internal import settings as core_settings
from dstack._internal.server import settings
from dstack._internal.server.identity import SERVER_REPLICA_ID
from dstack._internal.server.utils.common import PIPELINE_TASKS_PREFIX, SCHEDULED_TASKS_PREFIX
from dstack._internal.server.utils.logging import AsyncioCancelledErrorFilter
from dstack._internal.utils import otel as otel_utils


def configure(app: FastAPI, engine: AsyncEngine) -> None:
    if settings.OTEL_TRACES_ENABLED:
        _configure_tracing()
    if settings.OTEL_METRICS_ENABLED:
        _configure_metrics()
    if settings.OTEL_LOGS_ENABLED:
        _configure_log_export()
    if settings.OTEL_TRACES_ENABLED or settings.OTEL_METRICS_ENABLED:
        # The instrumentors emit both traces and metrics —
        # each signal is a no-op unless its provider is configured
        _instrument(app, engine)


def _configure_tracing() -> None:
    otel_utils.configure_tracing(
        _get_resource(), ParentBased(root=_build_root_sampler()), OTLPSpanExporter()
    )


def _build_root_sampler() -> otel_utils.RootSpanNameSampler:
    background_rate = settings.OTEL_TRACES_BACKGROUND_SAMPLE_RATE
    return otel_utils.RootSpanNameSampler(
        default_rate=settings.OTEL_TRACES_SAMPLE_RATE,
        rates_by_name_prefix={
            SCHEDULED_TASKS_PREFIX: background_rate,
            PIPELINE_TASKS_PREFIX: background_rate,
        },
    )


def _configure_metrics() -> None:
    readers: List[MetricReader] = []
    for exporter in _get_metrics_exporters():
        if exporter == "prometheus":
            # Registers into the default prometheus_client registry
            # served by the /metrics endpoint
            readers.append(PrometheusMetricReader())
        elif exporter == "otlp":
            readers.append(PeriodicExportingMetricReader(OTLPMetricExporter()))
        else:
            raise ValueError(
                f"Unknown exporter {exporter!r} in DSTACK_OTEL_METRICS_EXPORTERS."
                " Supported exporters: prometheus, otlp"
            )
    otel_utils.configure_metrics(_get_resource(), readers)


def _configure_log_export() -> None:
    otel_utils.configure_log_export(
        _get_resource(), OTLPLogExporter(), filters=[AsyncioCancelledErrorFilter()]
    )


def _instrument(app: FastAPI, engine: AsyncEngine) -> None:
    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
    _register_db_span_renaming(engine.sync_engine)
    HTTPXClientInstrumentor().instrument()
    # unixsocket calls to runners should not be instrumented: every runner
    # tunnel has a unique socket path that becomes the net.peer.name metric
    # attribute, so the SDK would accumulate state for an unbounded number of series.
    RequestsInstrumentor().instrument(excluded_urls=r"http\+unix://")
    if settings.OTEL_METRICS_ENABLED:
        SystemMetricsInstrumentor(config=otel_utils.PROCESS_METRICS_CONFIG).instrument()


def _get_metrics_exporters() -> List[str]:
    # OTLP by default, like traces and logs. The prometheus exporter (metrics on
    # the /metrics endpoint) is opt-in: scraping /metrics through a load
    # balancer with multiple server replicas interleaves the replicas' counters
    # into the same series, silently corrupting rates.
    if settings.OTEL_METRICS_EXPORTERS is not None:
        return [e.strip() for e in settings.OTEL_METRICS_EXPORTERS.split(",") if e.strip()]
    return ["otlp"]


def _get_resource() -> Resource:
    return Resource.create(
        {
            "service.name": "dstack-server",
            # Distinguishes replicas: without it, metrics pushed by multiple
            # server replicas collapse into the same series, corrupting counters
            "service.instance.id": SERVER_REPLICA_ID,
            "service.version": core_settings.DSTACK_VERSION or "dev",
            "deployment.environment.name": settings.SERVER_ENVIRONMENT,
        }
    )


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
