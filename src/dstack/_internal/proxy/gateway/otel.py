import logging
from typing import Literal, Optional

from fastapi import FastAPI
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPX2ClientInstrumentor, HTTPXClientInstrumentor
from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.sampling import ParentBased

from dstack._internal import settings as core_settings
from dstack._internal.proxy.gateway.models import OTelSettings
from dstack._internal.utils import otel as otel_utils
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

_AUTH_SPAN_NAME_PREFIX = "GET /api/auth/"

_applied_settings: Optional[OTelSettings] = None


def instrument(app: FastAPI) -> None:
    """Must be called before the app starts serving. No-op until `apply_settings` is called."""
    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
    HTTPX2ClientInstrumentor().instrument()
    SystemMetricsInstrumentor(config=otel_utils.PROCESS_METRICS_CONFIG).instrument()


def apply_settings(settings: Optional[OTelSettings]) -> bool:
    """
    Returns True if the app must be restarted to apply `settings`,
    since OpenTelemetry providers can only be set once per process.
    """
    global _applied_settings
    if settings is not None and not settings.any_enabled:
        settings = None
    if settings == _applied_settings:
        return False
    if _applied_settings is not None:
        logger.info("OpenTelemetry settings changed, the gateway app needs a restart")
        return True
    assert settings is not None
    # Set before configuring, since a failed configuration cannot be retried in this process
    _applied_settings = settings
    try:
        _configure(settings)
    except Exception:
        logger.exception("Failed to configure OpenTelemetry")
    return False


def _configure(settings: OTelSettings) -> None:
    resource = _get_resource(settings)
    if settings.traces_enabled:
        otel_utils.configure_tracing(
            resource,
            ParentBased(root=_build_root_sampler(settings)),
            OTLPSpanExporter(
                endpoint=_get_signal_endpoint(settings, "traces"), headers=settings.headers
            ),
        )
    if settings.metrics_enabled:
        exporter = OTLPMetricExporter(
            endpoint=_get_signal_endpoint(settings, "metrics"), headers=settings.headers
        )
        otel_utils.configure_metrics(resource, [PeriodicExportingMetricReader(exporter)])
    if settings.logs_enabled:
        otel_utils.configure_log_export(
            resource,
            OTLPLogExporter(
                endpoint=_get_signal_endpoint(settings, "logs"), headers=settings.headers
            ),
            # The app logs at DEBUG level to journald, which would be too noisy to export
            level=logging.INFO,
        )


def _build_root_sampler(settings: OTelSettings) -> otel_utils.RootSpanNameSampler:
    return otel_utils.RootSpanNameSampler(
        default_rate=settings.traces_sample_rate,
        rates_by_name_prefix={_AUTH_SPAN_NAME_PREFIX: settings.traces_auth_sample_rate},
    )


def _get_signal_endpoint(
    settings: OTelSettings, signal: Literal["traces", "metrics", "logs"]
) -> str:
    return f"{settings.endpoint.rstrip('/')}/v1/{signal}"


def _get_resource(settings: OTelSettings) -> Resource:
    return Resource.create(
        {
            **settings.resource_attributes,
            "service.name": "dstack-gateway",
            "service.version": core_settings.DSTACK_VERSION or "dev",
        }
    )
