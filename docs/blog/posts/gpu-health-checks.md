---
title: Introducing passive GPU health checks
date: 2025-08-12
description: "TBA"  
slug: gpu-helth-checks
image: https://dstack.ai/static-assets/static-assets/images/gpu-health-checks.png
categories:
  - Changelog
---

# Introducing passive GPU health checks

In large-scale training, a single bad GPU can derail progress. Sometimes the failure is obvious — jobs crash outright. Other times it’s subtle: correctable memory errors, intermittent instability, or thermal throttling that quietly drags down throughput. In big experiments, these issues can go unnoticed for hours or days, wasting compute and delaying results.

`dstack` already supports GPU telemetry monitoring through NVIDIA DCGM [metrics](../../docs/guides/metrics.md), covering utilization, memory, and temperature. This release extends that capability with passive hardware health checks powered by DCGM [background health checks](https://docs.nvidia.com/datacenter/dcgm/latest/user-guide/feature-overview.html#background-health-checks). With these, `dstack` continuously evaluates fleet GPUs for hardware reliability and displays their status before scheduling workloads.

<img src="https://dstack.ai/static-assets/static-assets/images/gpu-health-checks.png" width="630"/>

<!-- more -->

## Why this matters

Multi-GPU and multi-node workloads are only as strong as their weakest component. GPU cloud providers increasingly rely on automated health checks to prevent degraded hardware from reaching customers. Problems can stem from ECC memory errors, faulty PCIe links, overheating, or other hardware-level issues. Some are fatal, others allow the GPU to run but at reduced performance or with higher failure risk.

Passive checks like these run in the background. They continuously monitor hardware telemetry and system events, evaluating them against NVIDIA’s known failure patterns — all without pausing workloads.

## How it works in dstack

`dstack` automatically queries DCGM for each fleet instance and appends a health status:

* An `idle` status means no issues have been detected.
* An `idle (warning)` status indicates a non-fatal issue, such as a correctable ECC error. The instance remains usable but should be monitored.
* An `idle (failure)` status points to a fatal issue, and the instance is automatically excluded from scheduling.

<div class="termy">

```shell
$ dstack fleet

 FLEET     INSTANCE  BACKEND          RESOURCES  STATUS          PRICE   CREATED
 my-fleet  0         aws (us-east-1)  T4:16GB:1  idle            $0.526  11 mins ago
           1         aws (us-east-1)  T4:16GB:1  idle (warning)  $0.526  11 mins ago
           2         aws (us-east-1)  T4:16GB:1  idle (failure)  $0.526  11 mins ago
```

</div>

A healthy instance is ready for workloads. A warning means you should monitor it closely. A failure removes it from scheduling entirely.

## Passive vs active checks

This release focuses on passive checks using DCGM background health checks. These run continuously and do not interrupt workloads.

For active checks today, you can run [NCCL tests](../../examples/clusters/nccl-tests/index.md) as a [distributed task](../../docs/concepts/tasks.md#distributed-tasks) to verify GPU-to-GPU communication and bandwidth across a fleet. Active tests like these can reveal network or interconnect issues that passive monitoring might miss. More built-in support for active diagnostics is planned.

## Supported backends

Passive GPU health checks work on AWS (except with custom `os_images`), Azure (except A10 GPUs), GCP, OCI, and [SSH fleets](../../docs/concepts/fleets.md#ssh) where DCGM is installed and configured for background checks. 

> Fleets created before version 0.19.22 need to be recreated to enable this feature.

## Looking ahead

This update is about visibility: giving engineers real-time insight into GPU health before jobs run. Next comes automation — policies to skip GPUs with warnings, and self-healing workflows that replace unhealthy instances without manual steps.

If you have experience with GPU reliability or ideas for automated recovery, join the conversation on
[Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"}.

!!! info "What's next?"
    1. Check [Quickstart](../../docs/quickstart.md)
    2. Explore the [clusters](../../docs/guides/clusters.md) guide
    3. Learn more about [metrics](../../docs/guides/metrics.md)
    4. Join [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"}
