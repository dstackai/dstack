---
title: "Exporting fleet and run metrics to Prometheus"
date: 2025-04-01
description: "TBA"
slug: prometheus
image: https://dstack.ai/static-assets/static-assets/images/dstack-prometheus-v3.png
categories:
  - Changelog
---

# Exporting GPU, cost, and other metrics to Prometheus

## Why Prometheus { style="display:none" }

Effective AI infrastructure management requires full visibility into compute performance and costs. AI researchers need
detailed insights into container- and GPU-level performance, while managers rely on cost metrics to track resource usage
across projects.

While `dstack` provides key metrics through its UI and [`dstack metrics`](dstack-metrics.md) CLI, teams often need more granular data and prefer
using their own monitoring tools. To support this, we’ve introduced a new endpoint that allows real-time exporting all collected
metrics—covering fleets and runs—directly to Prometheus.

<img src="https://dstack.ai/static-assets/static-assets/images/dstack-prometheus-v3.png" width="630"/>

<!-- more -->

## How to set it up

To collect and export fleet and run metrics to Prometheus, set the
`DSTACK_ENABLE_PROMETHEUS_METRICS` environment variable. Once the server is running, configure Prometheus to pull
metrics from `<dstack server URL>/metrics`.

Once Prometheus is set up, it will automatically pull metrics from the `dstack` server at the defined interval.

With metrics now in Prometheus, you can use Grafana to create dashboards, whether to monitor all projects at once or
drill down into specific projects or users.

<img src="https://dstack.ai/static-assets/static-assets/images/dstack-prometheus-grafana-dark.png" width="800"/>

Overall, `dstack` collects three groups of metrics:

| Group      | Description                                                                                                                                                       |
|------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Fleets** | Fleet metrics include details for each instance, such as running time, price, GPU name, and more.                                                                 |
| **Runs**   | Run metrics include run counters for each user in each project.                                                                                                   |
| **Jobs**   | A run consists of one or more jobs, each mapped to a container. Job metrics offer insights into execution time, cost, GPU model, NVIDIA DCGM telemetry, and more. |

For a full list of available metrics and labels, check out [Metrics](../../docs/guides/metrics.md).

??? info "NVIDIA"
    NVIDIA DCGM metrics are automatically collected for `aws`, `azure`, `gcp`, and `oci` backends,
    as well as for [SSH fleets](../../docs/concepts/fleets.md#ssh).

    To ensure NVIDIA DCGM metrics are collected from SSH fleets, ensure the `datacenter-gpu-manager-4-core`,
    `datacenter-gpu-manager-4-proprietary`, and `datacenter-gpu-manager-exporter` packages are installed on the hosts.

??? info "AMD"
    AMD device metrics are not yet collected for any backends. This support will be available soon. For now, AMD metrics are
    only accessible through the UI and the [`dstack metrics`](dstack-metrics.md) CLI.

!!! info "What's next?"
    1. See [Metrics](../../docs/guides/metrics.md)
    1. Check [dev environments](../../docs/concepts/dev-environments.md),
       [tasks](../../docs/concepts/tasks.md), [services](../../docs/concepts/services.md),
       and [fleets](../../docs/concepts/fleets.md)
    2. Join [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"}
