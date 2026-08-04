---
title: "Monitoring essential GPU metrics via CLI"
date: 2024-10-22
description: "dstack introduces a new CLI command (and API) for monitoring container metrics, incl. GPU usage for NVIDIA, AMD, and other accelerators."  
slug: dstack-metrics
image: https://dstack.ai/static-assets/static-assets/images/dstack-stats-v2.png
categories:
  - Changelog
---

# Monitoring essential GPU metrics via CLI

## How it works { style="display:none"}

While it's possible to use third-party monitoring tools with `dstack`, it is often more convenient to debug your run and
track metrics out of the box. That's why, with the latest release, `dstack` introduced [`dstack stats`](../../docs/reference/cli/dstack/metrics.md), a new CLI (and API)
for monitoring container metrics, including GPU usage for `NVIDIA`, `AMD`, and other accelerators.

<div class="termy">

```shell
$ dstack metrics llama-70b-sft

        UTILIZATION                            MEMORY
 cpu    ▅▄▄▄▃▃▃▃▃▃▃▃▃▃▃▃▅▅▄▂▃▃▃▃▃▃▃ 39% of 64  ▃▃▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄ 297GB/480GB

 gpu=0  ▁▂▃▆▆▆▆▆▆▆▆▆▆▆▆▆▆▁▆▆▆▆▆▆▆▆▆ 89%        ▄▅▅▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆ 67GB/80GB
 gpu=1  ▁▂▆▆▆▅▆▆▆▆▆▆▆▆▆▆▁▁▅▆▆▅▆▆▆▆▆ 84%        ▄▅▅▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆ 67GB/80GB
 gpu=2  ▁▂▆▆▆▆▆▆▆▆▆▆▆▆▆▆▁▆▆▆▆▆▆▆▆▆▆ 87%        ▄▅▅▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆ 67GB/80GB
 gpu=3  ▂▃▆▅▅▅▅▅▅▆▅▅▆▆▆▆▁▅▅▅▅▅▆▅▅▅▅ 82%        ▄▅▅▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆▆ 67GB/80GB

        4 Aug 11:35 ─────────── now            4 Aug 11:35 ─────────── now
```

</div>

<!-- more -->

> Note, the `dstack stats` command has been renamed to `dstack metrics`. The old name is also supported by deprecated.

The command is similar to `kubectl top` (in terms of semantics) and `docker stats` (in terms of the CLI interface). The key
difference is that `dstack stats` includes GPU VRAM usage and GPU utilization percentage. 

>The feature works right away with `NVIDIA` and `AMD`, whether you're running a development environment, task, or service.
> `TPU` support is coming soon.

Similar to `kubectl top`, if a run consists of multiple jobs (such as distributed training or an auto-scalable service),
`dstack stats` will display metrics per job.

> Note, `dstack metrics` now shows one job at a time, like `dstack logs`. Use `--replica` and `--job` to
> choose it; both default to `0`.

!!! info "HTTP API"
    In addition to the `dstack stats` CLI commands, metrics can be obtained via the
    [`/api/project/{project_name}/metrics/job/{run_name}`](../../docs/reference/http/metrics.md) HTTP endpoint.

## Why monitor GPU usage

Kubernetes and Docker don’t offer built-in support for GPU usage tracking. Since `dstack` is tailored for AI containers, we
consider native GPU monitoring essential. 

#### GPU  usage

Monitoring GPU memory usage in AI workloads helps prevent out-of-memory errors and provides a clearer picture of how
much memory is actually used or needed by the workload.

#### GPU utilization

Monitoring GPU utilization is important for identifying under-utilization and ensuring that workloads are distributed
evenly across GPUs.

## Roadmap

Monitoring is a critical part of observability, and we have many more features on our roadmap:

* Potentially adding more metrics, including disk usage, I/O, network, etc
* Support for the TPU accelerator
* Displaying historical metrics within the control plane UI
* Tracking deployment metrics, including LLM-related metrics
* A simple way to export metrics to Prometheus

## Feedback

If you find something not working as intended, please be sure to report it to
our [bug tracker](https://github.com/dstackai/dstack/issues){:target="_ blank"}. 
Your feedback and feature requests are also very welcome on both 
[Discord](https://discord.gg/u8SmfwPpMd) and the
[issue tracker](https://github.com/dstackai/dstack/issues).
