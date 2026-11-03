---
title: "Serve GLM-5.3 Coding Agents Faster and Cheaper on GB200 NVL72"
date: 2026-11-02
description: "Optimized with dstack presets, 14 GB200 NVL72 nodes serve 48 GLM-5.3 coding agents as fast as the three fastest OpenRouter endpoints, with lower p50 TTFT, and self-hosting them costs under a third of buying the same tokens."
slug: glm53-gb200-nvl72-coding-agents
image: https://dstack.ai/static-assets/static-assets/images/dstack-glm-53-gb200-nvl72-crusoe.png
categories:
  - Benchmarks
---

# Serve GLM-5.3 Coding Agents Faster and Cheaper on GB200 NVL72

With `dstack` [presets](../../docs/concepts/presets.md), the preset agent optimized a GB200 NVL72 fleet to serve GLM-5.3 coding agents as fast as the three fastest endpoints on OpenRouter, with lower p50 TTFT. Self-hosting them this way costs under a third of buying the same tokens from those endpoints. By a coding agent we mean one session of a tool like Claude Code: a multi-turn conversation that resends its whole context, about 135k tokens, on every request and spawns subagents along the way.

<img src="https://dstack.ai/static-assets/static-assets/images/dstack-glm-53-gb200-nvl72-crusoe.png" width="630" />

This work was done jointly with [Crusoe](https://crusoe.ai), who provided the GB200 NVL72 capacity.

<!-- more -->

On 14 GB200 nodes, 48 agents get the same p50 output speed per user as the three fastest GLM-5.3 endpoints on OpenRouter, about 3x lower p50 TTFT, and 2x or more higher output speed at p99, where a coding agent's slowest turns are. Serving the same work ourselves costs $12.77 per million output tokens, against $43–66 when buying it from these endpoints.

=== "tok/s/user p50"
    <img src="https://dstack.ai/static-assets/static-assets/images/glm53-gb200-nvl72-coding-agents-fig-1.png" width="750" />

=== "tok/s/user p99"
    <img src="https://dstack.ai/static-assets/static-assets/images/glm53-gb200-nvl72-coding-agents-fig-2.png" width="750" />

=== "TTFT p50"
    <img src="https://dstack.ai/static-assets/static-assets/images/glm53-gb200-nvl72-coding-agents-fig-3.png" width="750" />

=== "TTFT p99"
    <img src="https://dstack.ai/static-assets/static-assets/images/glm53-gb200-nvl72-coding-agents-fig-4.png" width="750" />

=== "Cost"
    <img src="https://dstack.ai/static-assets/static-assets/images/glm53-gb200-nvl72-coding-agents-fig-5.png" width="750" />

> Provider figures are OpenRouter's for 19–26 October. Output speed follows OpenRouter's definition: output tokens per second from sending the request to the end of the response, TTFT included. The self-hosting cost is 56 chips at [$4.00 per chip-hour](https://inferencex.semianalysis.com/chips/gb200-nvl72) divided by the 17.54 million output tokens the fleet produces per hour. The cost of buying applies each endpoint's list prices, including cache-read prices, to our exact token counts.

## Purpose

We want to optimize a GB200 NVL72 fleet for GLM-5.3 coding agents and find out three things: how fast it serves them and what that costs against buying the same tokens from providers, how many agents it holds, and which layout fits an agentic load best.

The last question is open because GB200 NVL72 is a multi-node machine. A fleet can be aggregated or prefill-decode (PD) disaggregated, split into a few wide engines or many narrow ones (TP4, TP8, TP16), parallelized in different ways (expert parallelism, data-parallel attention, decode context parallelism), and keep the cache in GPU memory or extend it into host memory.

## Setup

| | Aggregated | PD disaggregated |
|---|---|---|
| GB200 nodes | 14 (56 GPUs) | 16 (64 GPUs) |
| Inference engine | SGLang | SGLang |
| Router | SGLang Model Gateway | Dynamo |

* Model: GLM-5.3, NVFP4 checkpoint (`nvidia/GLM-5.3-NVFP4`)
* Orchestration: `dstack`
* Optimization: `dstack` presets with model: Claude Opus 5

Each GB200 node has 4 GPUs, 744 GB of GPU memory and 881 GB of CPU memory. The router ran on a separate CPU node with 32 vCPUs and 128 GB of RAM, in the same private network. The GB200 NVL72 cluster was provided by [Crusoe](https://crusoe.ai):

<img src="https://dstack.ai/static-assets/static-assets/images/glm53-gb200-nvl72-coding-agents-crusoe.png" width="750" />

## Methodology

### Workload

The agents are replayed from SemiAnalysis's AgentX benchmark, built from 393 recorded Claude Code sessions. One agent is one session, and it fans out into subagents, so several of its requests can be in flight at once. A request carries about 135k input tokens, 96% of them a prefix the server has already seen, and returns about 1k tokens.

Each benchmark run lasts 900 seconds. Real sessions pause between requests while the user reads a reply or a tool runs. We capped those pauses at 5 seconds to keep the runs short, which makes the load heavier than real agents produce: 48 agents kept about 39 requests in flight.

### Optimization

The preset agent runs every candidate configuration as a benchmarked trial and verifies the winner as a deployable service. Sessions are chained, so later sessions inherit the trial records of earlier ones. Every session ran five trials under the same constraints: a 1M-token context and a p50 TTFT of at most 1 s, raised to 3 s at 128 and 192 agents.

> The objective was to optimize the layout: we did not ask the preset agent to patch SGLang or write kernels. The whole study took about two days.

The baseline is the SGLang cookbook recipe for GLM-5.3 NVFP4. The cookbook publishes it for a single GB300 node; on GB200 it ran as seven two-node TP8 engines.

## Results

### Aggregated wins while caches fit

The preset agent was not told which layout to use. Its PD attempts failed to reach a benchmark because of setup problems, so it stayed with aggregated and, over three sessions, converged on seven two-node TP8 engines with HiCache, which keeps context evicted from GPU memory in host memory. Throughput rose from 2,188 to 5,114 tok/s (+134%) and p50 TTFT fell from 383 to 293 ms (−23%), with no source patches.

<img src="https://dstack.ai/static-assets/static-assets/images/glm53-gb200-nvl72-coding-agents-fig-6.png" width="750" />

1. Wider engines with data-parallel attention held more KV cache but paid for it in communication between GPUs: +25% in session 1.
2. Decode context parallelism split each session's cache across eight GPUs for about 5x the capacity, but combining partial attention results on every decode step ate the gain. Seven TP8 engines with 140 GB of host-memory cache per GPU rank kept decode steps fast and won session 2 at 4,412 tok/s. The session's baseline dropped to 1,642 tok/s because the preset agent first removed session 1's odd fourth engine.
3. Single-node TP4 engines decoded faster but processed long prompts slower, losing 28%. Back on TP8, a write-back HiCache policy and SGLang's newer speculative decoding path brought session 3 to 5,114 tok/s at 293 ms.

### PD helps only at high load

We then asked the preset agent to make PD work and use it on every trial. At 48 agents its best was 3,693 tok/s at 887 ms p50 TTFT on 16 nodes, still behind aggregated's 5,114 tok/s at 293 ms on 14. With data-parallel attention its decode steps took longer, and only four engines generated replies against aggregated's seven.

<img src="https://dstack.ai/static-assets/static-assets/images/glm53-gb200-nvl72-coding-agents-fig-7.png" width="750" />

1. Rebalancing prefill and decode from 1:3 to 1:1 nodes brought p50 TTFT from 1,447 to 762 ms, under the 1 s budget.
2. At 128 agents, the preset agent started from SemiAnalysis's published layout with the engine count doubled to fill 64 GPUs. Splitting the DEP16 decode engines into DEP8 cut the decode step from 35.7 to 24.5 ms and raised throughput 32%, to 8,599 tok/s at 2,035 ms.
3. At 192 agents, giving decode more KV memory reached 10,808 tok/s, 1.8x aggregated's throughput per chip, but p50 TTFT rose to 3,170 ms, more than 10x aggregated's and over the 3 s budget.

At 128 agents, the PD configuration matches SemiAnalysis's [InferenceX run](https://github.com/SemiAnalysisAI/InferenceX/actions/runs/37506762704/job/112417831364) on GB200 NVL72 per chip: 134.4 against 136.4 output tok/s, at a similar 2.07 against 2.27 requests in flight per chip. Their run served GLM-5.2, which has the same architecture as GLM-5.3.

### Cache overflow hurts aggregated

We then raised the agent count for each winner. Aggregated, replayed at normal pace with pauses capped at 300 s instead of 5 s, rose from 2,150 tok/s at 48 agents to 3,722 at 120, then fell to 2,307 at 240 as cache reuse dropped from 97.2% to 76.6% and p99 TTFT reached 690 s. PD, at the accelerated pace, kept cache reuse around 95% and rose from 3,530 tok/s at 48 agents to 10,545 at 192, while p50 TTFT climbed from 727 ms to 3,250 ms.

## Conclusion

### Self-hosting beats buying tokens

Optimized for 48 agents, 14 GB200 nodes match the fastest GLM-5.3 endpoints on p50 output speed and beat them on p50 TTFT and on output speed at p99. Self-hosting costs $12.77 per million output tokens, against $43–66 to buy the same tokens from these endpoints.

### Choose the layout by load

Aggregated is faster while the sessions' caches fit in memory: there is no KV transfer, all seven engines generate replies, and cache-aware routing sends each session back to the engine that holds its context. PD keeps more context reusable as load grows, so it produces more tokens per chip, but each agent waits longer for its first token.

### Cache memory caps agent capacity

How many agents a fleet holds depends on whether their caches fit and reuse stays high, not on a fixed number; for our aggregated fleet it was 48 at the accelerated pace. Aggregated duplicates the KV cache across the GPUs of each TP8 engine, so once GPU and host memory fill up, evicted context has to be recomputed and throughput falls. PD scaled to 192 agents on throughput, but not on TTFT. The aggregated configuration was optimized for 48 agents, so its higher-load runs test that configuration rather than one tuned for them.

### Layout drove most gains

Almost all of the gain came from layout decisions: whether to disaggregate, how many engines, how wide, and whether to extend the cache into host memory. The preset agent found them in about two days, without patching the engine or writing kernels, which remain open for further gains.

## Limitations

1. Replayed, accelerated traffic. The pauses are capped at 5 s and the prompt text is generated, so production traffic will differ in cache reuse, timing and concurrency. For production, give presets your own traffic as the workload.
2. Not a controlled comparison with providers. Their figures come from OpenRouter's measurements of different traffic, and we serve the NVFP4 checkpoint while Baseten's fast endpoints serve FP8. The cost comparison is make or buy: it sets the cost of self-hosting against the price of buying the same tokens, not against what providers pay to serve them. It assumes the fleet runs this load continuously at $4.00 per chip-hour, [SemiAnalysis's retail price](https://inferencex.semianalysis.com/chips/gb200-nvl72) for GB200 NVL72.
3. Layout first. The preset agent spent its sessions on layout rather than engine settings, source patches or kernels, so more gains are likely.
4. The comparison with SemiAnalysis is approximate. Their run served the GLM-5.2 NVFP4 checkpoint, which has the same architecture but a different quantization recipe. The SGLang builds also differ, we used 64 chips against their 32, and our benchmark window was 929 s against their 3,625 s, so we compare only throughput per chip.

## Deploy

Both presets are public: [aggregated](https://sky.dstack.ai/presets/dstackai/glm53-gb200-nvl72-agentic-c48) and [PD disaggregated](https://sky.dstack.ai/presets/dstackai/glm53-gb200-nvl72-agentic-pd-c128). They can be deployed via `dstack` to any GPU cloud, Kubernetes, or bare-metal cluster with GB200 NVL72 nodes and a CPU node for the router.

To deploy on Crusoe, use `dstack`'s native integration: it can provision [VMs](../../docs/examples/clusters/crusoe.md#vms) through the `crusoe` backend or use a [Kubernetes](../../docs/examples/clusters/crusoe.md#kubernetes) cluster through the `kubernetes` backend. Any other nodes can be added as an [SSH fleet](../../docs/concepts/fleets.md).

Once the fleet is created, pull a preset, export it as a service configuration, and apply it:

=== "Aggregated"

    <div class="termy">

    ```shell
    $ dstack preset pull dstackai/glm53-gb200-nvl72-agentic-c48
    $ dstack preset export dstackai/glm53-gb200-nvl72-agentic-c48 -f glm53-c48.dstack.yml
    $ dstack apply -f glm53-c48.dstack.yml
    ```

    </div>

=== "PD disaggregated"

    <div class="termy">

    ```shell
    $ dstack preset pull dstackai/glm53-gb200-nvl72-agentic-pd-c128
    $ dstack preset export dstackai/glm53-gb200-nvl72-agentic-pd-c128 -f glm53-pd-c128.dstack.yml
    $ dstack apply -f glm53-pd-c128.dstack.yml
    ```

    </div>

## Thanks to our partners

### Crusoe

This work was done jointly with [Crusoe](https://crusoe.ai), who provided the GB200 NVL72 capacity for it. We are sincerely grateful for their compute and support.

> If you'd like to rent high-quality GPU clusters, including GB200 NVL72, for training or inference, we recommend going with Crusoe.

_Special thanks to **Martin Cala** and **Michael YenChi Ho** from the Crusoe team for their help and technical assistance throughout this work._
