from contextlib import suppress

import prometheus_client


def unregister_default_collectors() -> None:
    """Removes the collectors prometheus_client registers by default.

    The default collectors (process_*, python_gc_*, python_info) are per-process:
    scraping them through a load balancer with multiple server replicas interleaves
    the replicas' values into the same series, corrupting them. Process metrics
    are available via OpenTelemetry instead, with a per-replica identity.
    """
    for collector in (
        prometheus_client.PROCESS_COLLECTOR,
        prometheus_client.PLATFORM_COLLECTOR,
        prometheus_client.GC_COLLECTOR,
    ):
        with suppress(KeyError):
            prometheus_client.REGISTRY.unregister(collector)
