from typing import Optional

from prometheus_client import Counter, Histogram


class RunMetrics:
    """Wrapper class for run-related Prometheus metrics."""

    def __init__(self):
        # submit_to_provision_duration reflects real provisioning time
        # but does not reflect how quickly provisioning processing works
        # since it includes scheduling time, retrying, etc.
        self._submit_to_provision_duration = Histogram(
            "dstack_submit_to_provision_duration_seconds",
            "Time from when a run has been submitted and first job provisioning",
            # Buckets optimized for percentile calculation
            buckets=[
                15,
                30,
                45,
                60,
                90,
                120,
                180,
                240,
                300,
                360,
                420,
                480,
                540,
                600,
                900,
                1200,
                1800,
                float("inf"),
            ],
            labelnames=["project_name", "run_type"],
        )

        self._pending_runs_total = Counter(
            "dstack_pending_runs_total",
            "Number of pending runs",
            labelnames=["project_name", "run_type"],
        )

    def log_submit_to_provision_duration(
        self, duration_seconds: float, project_name: str, run_type: str
    ):
        self._submit_to_provision_duration.labels(
            project_name=project_name, run_type=run_type
        ).observe(duration_seconds)

    def increment_pending_runs(self, project_name: str, run_type: str):
        self._pending_runs_total.labels(project_name=project_name, run_type=run_type).inc()


run_metrics = RunMetrics()


class HTTPMetrics:
    """Wrapper class for server HTTP Prometheus metrics.

    Deprecated in favor of the OpenTelemetry HTTP metrics
    (`DSTACK_OTEL_METRICS_ENABLED`), which are correct in multi-replica
    deployments. Kept for backward compatibility.
    """

    def __init__(self):
        self._requests_total = Counter(
            "dstack_server_requests_total",
            "Total number of HTTP requests",
            labelnames=["method", "endpoint", "http_status", "project_name"],
        )
        self._request_duration = Histogram(
            "dstack_server_request_duration_seconds",
            "HTTP request duration in seconds",
            labelnames=["method", "endpoint", "http_status", "project_name"],
        )

    def log_request(
        self,
        method: str,
        endpoint: str,
        http_status: int,
        project_name: Optional[str],
        duration_seconds: float,
    ):
        labels = {
            "method": method,
            "endpoint": endpoint,
            "http_status": http_status,
            "project_name": project_name,
        }
        self._request_duration.labels(**labels).observe(duration_seconds)
        self._requests_total.labels(**labels).inc()


http_metrics = HTTPMetrics()
