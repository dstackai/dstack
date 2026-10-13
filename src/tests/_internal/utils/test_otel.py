import asyncio
import logging

import pytest
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.sampling import Decision

from dstack._internal.server.utils.logging import AsyncioCancelledErrorFilter
from dstack._internal.utils.otel import RootSpanNameSampler, build_log_handler


@pytest.fixture
def log_exporter() -> InMemoryLogRecordExporter:
    return InMemoryLogRecordExporter()


@pytest.fixture
def logger_provider(log_exporter: InMemoryLogRecordExporter) -> LoggerProvider:
    logger_provider = LoggerProvider()
    logger_provider.add_log_record_processor(SimpleLogRecordProcessor(log_exporter))
    return logger_provider


class TestBuildLogHandler:
    def test_exports_records_with_trace_context(
        self, log_exporter: InMemoryLogRecordExporter, logger_provider: LoggerProvider
    ):
        logger = logging.getLogger("test_otel_logs")
        logger.addHandler(
            build_log_handler(logger_provider, filters=[AsyncioCancelledErrorFilter()])
        )

        # A local provider, as the global one can only be set once per process
        tracer = TracerProvider().get_tracer(__name__)
        with tracer.start_as_current_span("op") as span:
            logger.warning("something happened")
        try:
            logger.error("cancelled", exc_info=asyncio.CancelledError())
        except Exception:
            pass

        records = [d.log_record for d in log_exporter.get_finished_logs()]
        assert len(records) == 1
        assert records[0].body == "something happened"
        assert records[0].severity_text == "WARN"
        assert records[0].trace_id == span.get_span_context().trace_id

    def test_respects_level(
        self, log_exporter: InMemoryLogRecordExporter, logger_provider: LoggerProvider
    ):
        logger = logging.getLogger("test_otel_logs_level")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(build_log_handler(logger_provider, level=logging.INFO))

        logger.debug("noise")
        logger.info("signal")

        assert [d.log_record.body for d in log_exporter.get_finished_logs()] == ["signal"]

    def test_does_not_export_otel_sdk_records(
        self, log_exporter: InMemoryLogRecordExporter, logger_provider: LoggerProvider
    ):
        handler = build_log_handler(logger_provider)

        # An OTLP export failure logged by the SDK must not be re-exported —
        # that would be a feedback loop through the same failing exporter
        sdk_logger = logging.getLogger("opentelemetry.exporter.otlp.proto.http._log_exporter")
        sdk_logger.addHandler(handler)
        sdk_logger.error("Failed to export logs batch")

        assert log_exporter.get_finished_logs() == ()


class TestRootSpanNameSampler:
    def test_samples_at_rate_by_name_prefix(self):
        sampler = RootSpanNameSampler(
            default_rate=1.0, rates_by_name_prefix={"background.": 0.0, "auth ": 1.0}
        )
        default_result = sampler.should_sample(None, trace_id=123, name="GET /api/project")
        background_result = sampler.should_sample(None, trace_id=123, name="background.task")
        auth_result = sampler.should_sample(None, trace_id=123, name="auth check")
        assert default_result.decision == Decision.RECORD_AND_SAMPLE
        assert background_result.decision == Decision.DROP
        assert auth_result.decision == Decision.RECORD_AND_SAMPLE

    def test_describes_rates(self):
        sampler = RootSpanNameSampler(default_rate=0.5, rates_by_name_prefix={"bg.": 0.1})
        assert sampler.get_description() == "RootSpanNameSampler(default=0.5,'bg.'=0.1)"
