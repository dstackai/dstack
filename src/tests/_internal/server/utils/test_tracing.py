import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.sampling import Decision

from dstack._internal.server.utils import tracing
from dstack._internal.server.utils.otel.utils import _get_db_span_name, _RootSpanNameSampler

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
        assert task_span.context.trace_id != outer_span.context.trace_id


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


class TestRootSpanNameSampler:
    def test_samples_at_rate_by_name(self):
        sampler = _RootSpanNameSampler(default_rate=1.0, background_rate=0.0)
        http_result = sampler.should_sample(None, trace_id=123, name="GET /api/project")
        background_result = sampler.should_sample(
            None, trace_id=123, name="pipeline_tasks.VolumeWorker.process"
        )
        assert http_result.decision == Decision.RECORD_AND_SAMPLE
        assert background_result.decision == Decision.DROP
