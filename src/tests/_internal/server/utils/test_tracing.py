import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.sampling import Decision

from dstack._internal.server.utils import tracing
from dstack._internal.server.utils.otel.utils import (
    _build_root_sampler,
    _get_db_span_name,
    _get_metrics_exporters,
)

_span_exporter = InMemorySpanExporter()


@pytest.fixture
def span_exporter():
    # The global tracer provider can only be set once per process
    if not isinstance(trace.get_tracer_provider(), TracerProvider):
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(_span_exporter))
        trace.set_tracer_provider(provider)
    _span_exporter.clear()
    return _span_exporter


class TestInstrumentNamedTask:
    @pytest.mark.asyncio
    async def test_creates_root_span(self, span_exporter: InMemorySpanExporter):
        @tracing.instrument_pipeline_task("TestWorker.process")
        async def task():
            return 42

        assert await task() == 42
        spans = span_exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "pipeline_tasks.TestWorker.process"
        assert spans[0].parent is None

    @pytest.mark.asyncio
    async def test_each_run_starts_new_trace(self, span_exporter: InMemorySpanExporter):
        @tracing.instrument_named_task("task")
        async def task():
            pass

        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("outer"):
            await task()
        task_span, outer_span = span_exporter.get_finished_spans()
        assert task_span.name == "task"
        assert task_span.parent is None
        assert task_span.context is not None
        assert outer_span.context is not None
        assert task_span.context.trace_id != outer_span.context.trace_id


class TestRecordTaskRun:
    @pytest.mark.asyncio
    async def test_counts_runs_by_status(self):
        from opentelemetry import metrics
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import InMemoryMetricReader, NumberDataPoint

        reader = InMemoryMetricReader()
        # The global meter provider can only be set once per process
        if not isinstance(metrics.get_meter_provider(), MeterProvider):
            metrics.set_meter_provider(MeterProvider(metric_readers=[reader]))
        else:
            pytest.skip("global meter provider already set")

        @tracing.instrument_named_task("task")
        async def ok_task():
            return 1

        @tracing.instrument_named_task("task")
        async def failing_task():
            raise ValueError()

        await ok_task()
        await ok_task()
        with pytest.raises(ValueError):
            await failing_task()

        metrics_data = reader.get_metrics_data()
        assert metrics_data is not None
        points = metrics_data.resource_metrics[0].scope_metrics[0].metrics[0].data.data_points
        counts = {}
        for point in points:
            assert isinstance(point, NumberDataPoint)
            assert point.attributes is not None
            assert point.attributes["task"] == "task"
            counts[point.attributes["status"]] = point.value
        assert counts == {"success": 2, "error": 1}


class TestGetMetricsExporters:
    @pytest.mark.parametrize(
        ("exporters", "expected"),
        [
            (None, ["otlp"]),
            ("prometheus", ["prometheus"]),
            ("prometheus, otlp", ["prometheus", "otlp"]),
        ],
    )
    def test_returns_expected(self, monkeypatch, exporters, expected):
        from dstack._internal.server import settings

        monkeypatch.setattr(settings, "OTEL_METRICS_EXPORTERS", exporters)
        assert _get_metrics_exporters() == expected


class TestGetDBSpanName:
    @pytest.mark.parametrize(
        ("statement", "expected"),
        [
            ("SELECT * FROM instances WHERE id = ?", "SELECT instances"),
            ("select id\nfrom jobs join runs on ...", "SELECT jobs"),
            ("INSERT INTO volumes (id) VALUES (?)", "INSERT volumes"),
            ("UPDATE fleets SET status = ?", "UPDATE fleets"),
            ('DELETE FROM "users"', "DELETE users"),
            ("PRAGMA journal_mode=WAL;", "PRAGMA"),
            ("BEGIN", "BEGIN"),
            ("", None),
        ],
    )
    def test_returns_expected(self, statement, expected):
        assert _get_db_span_name(statement) == expected


class TestBuildRootSampler:
    def test_samples_background_tasks_at_background_rate(self, monkeypatch):
        from dstack._internal.server import settings

        monkeypatch.setattr(settings, "OTEL_TRACES_SAMPLE_RATE", 1.0)
        monkeypatch.setattr(settings, "OTEL_TRACES_BACKGROUND_SAMPLE_RATE", 0.0)
        sampler = _build_root_sampler()
        http_result = sampler.should_sample(None, trace_id=123, name="GET /api/project")
        pipeline_result = sampler.should_sample(
            None, trace_id=123, name="pipeline_tasks.VolumeWorker.process"
        )
        scheduled_result = sampler.should_sample(
            None, trace_id=123, name="scheduled_tasks.process_fleets"
        )
        assert http_result.decision == Decision.RECORD_AND_SAMPLE
        assert pipeline_result.decision == Decision.DROP
        assert scheduled_result.decision == Decision.DROP
