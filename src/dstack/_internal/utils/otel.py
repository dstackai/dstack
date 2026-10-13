import logging
from typing import TYPE_CHECKING, Mapping, Optional, Sequence

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.context import Context
from opentelemetry.instrumentation.logging.handler import LoggingHandler
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.sampling import Sampler, SamplingResult, TraceIdRatioBased
from opentelemetry.trace import Link, SpanKind
from opentelemetry.trace.span import TraceState
from opentelemetry.util.types import Attributes

from dstack._internal.utils.logging import get_logger

if TYPE_CHECKING:
    # Not available in older opentelemetry-sdk versions, which name it LogExporter
    from opentelemetry.sdk._logs.export import LogRecordExporter

logger = get_logger(__name__)

# Process-level metrics only. Host-level (`system.*`) metrics are left
# to node exporters. `process.runtime.*` metrics are deprecated duplicates.
PROCESS_METRICS_CONFIG = {
    "process.cpu.time": ["user", "system"],
    "process.cpu.utilization": ["user", "system"],
    "process.memory.usage": None,
    "process.memory.virtual": None,
    "process.thread.count": None,
    "process.open_file_descriptor.count": None,
    "process.context_switches": ["involuntary", "voluntary"],
    "cpython.gc.collections": None,
    "cpython.gc.collected_objects": None,
    "cpython.gc.uncollectable_objects": None,
}


def configure_tracing(resource: Resource, sampler: Sampler, exporter: SpanExporter) -> None:
    provider = TracerProvider(resource=resource, sampler=sampler)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    logger.info("OpenTelemetry tracing enabled")


def configure_metrics(resource: Resource, readers: Sequence[MetricReader]) -> None:
    provider = MeterProvider(resource=resource, metric_readers=readers)
    metrics.set_meter_provider(provider)
    logger.info("OpenTelemetry metrics enabled")


def configure_log_export(
    resource: Resource,
    exporter: "LogRecordExporter",
    level: int = logging.NOTSET,
    filters: Sequence[logging.Filter] = (),
) -> None:
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
    set_logger_provider(logger_provider)
    logging.getLogger().addHandler(build_log_handler(logger_provider, level, filters))
    logger.info("OpenTelemetry log export enabled")


def build_log_handler(
    logger_provider: LoggerProvider,
    level: int = logging.NOTSET,
    filters: Sequence[logging.Filter] = (),
) -> logging.Handler:
    handler = LoggingHandler(level=level, logger_provider=logger_provider)
    for log_filter in filters:
        handler.addFilter(log_filter)
    handler.addFilter(_OTelSDKLogFilter())
    return handler


class _OTelSDKLogFilter(logging.Filter):
    """Drops log records emitted by the OTel SDK itself.

    Exporting them would be a feedback loop: an OTLP export failure is logged,
    the record is queued for the same failing exporter, and so on indefinitely.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return not (record.name + ".").startswith("opentelemetry.")


class RootSpanNameSampler(Sampler):
    """Samples traces at different rates depending on the root span name prefix."""

    def __init__(self, default_rate: float, rates_by_name_prefix: Mapping[str, float]):
        self._default_sampler = TraceIdRatioBased(default_rate)
        self._samplers_by_name_prefix = {
            prefix: TraceIdRatioBased(rate) for prefix, rate in rates_by_name_prefix.items()
        }

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
        for prefix, prefix_sampler in self._samplers_by_name_prefix.items():
            if name.startswith(prefix):
                sampler = prefix_sampler
                break
        return sampler.should_sample(
            parent_context, trace_id, name, kind, attributes, links, trace_state
        )

    def get_description(self) -> str:
        return "RootSpanNameSampler"
