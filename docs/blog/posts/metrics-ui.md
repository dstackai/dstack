---
title: "Built-in UI for monitoring essential GPU metrics"
date: 2025-04-03
description: "TBA"
slug: metrics-ui
image: https://dstack.ai/static-assets/static-assets/images/dstack-metrics-ui-v3-min.png
categories:
  - Changelog
---

# Built-in UI for monitoring essential GPU metrics

AI workloads generate vast amounts of metrics, making it essential to have efficient monitoring tools. While our recent
update introduced the ability to export available metrics to Prometheus for maximum flexibility, there are times when
users need to quickly access essential metrics without the need to switch to an external tool.

<img src="https://dstack.ai/static-assets/static-assets/images/dstack-metrics-ui-v3-min.png" width="630"/>

Previously, we introduced a [CLI command](dstack-metrics.md) that allows users to view essential GPU metrics for both NVIDIA
and AMD hardware. Now, with this latest update, we’re excited to announce the addition of a built-in dashboard within
the `dstack` control plane.

<!-- more -->

The new feature provides an easy-to-use interface for tracking the most essential GPU metrics
directly from the control plane, streamlining the real-time monitoring process without needing any additional tools.

<img src="https://dstack.ai/static-assets/static-assets/images/dstack-metrics-ui-dashboard.png" width="800">

Additionally, we’ve renamed the CLI command previously known as `dstack stats` to `dstack metrics` for consistency.

<div class="termy">

```shell
$ dstack metrics nccl-tests -w
 NAME        CPU  MEMORY            GPU
 nccl-tests  81%  2754MB/1638400MB  #0 100740MB/144384MB 100% Util
                                    #1 100740MB/144384MB 100% Util
                                    #2 100740MB/144384MB 99% Util
                                    #3 100740MB/144384MB 99% Util
                                    #4 100740MB/144384MB 99% Util
                                    #5 100740MB/144384MB 99% Util
                                    #6 100740MB/144384MB 99% Util
                                    #7 100740MB/144384MB 100% Util
```

</div>

By default, both the control plane and CLI show metrics from the last hour, which is particularly useful for debugging
workloads. 

For persistent storage and long-term access to metrics, we still recommend setting up Prometheus to fetch
metrics from `dstack`.

!!! info "What's next?"
    1. See [Metrics](../../docs/guides/metrics.md)
    2. Check [dev environments](../../docs/concepts/dev-environments.md), [tasks](../../docs/concepts/tasks.md), [services](../../docs/concepts/services.md), and [fleets](../../docs/concepts/fleets.md)
    3. Join [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"}
