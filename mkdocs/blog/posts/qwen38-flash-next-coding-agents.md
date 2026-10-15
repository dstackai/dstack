---
title: "Serve Fastest Qwen3.8-Flash-Next Coding Agents on 4xH200"
date: 2026-10-15
description: "Optimized with dstack presets, a single 4xH200 node serves 16 concurrent Qwen3.8-Flash-Next coding agents with roughly 3x lower latency than the available providers."
slug: qwen38-flash-next-coding-agents
image: https://dstack.ai/static-assets/static-assets/images/dstack-qwen-38-flash-next-jarvis.png
categories:
  - Benchmarks
---

# Serve Fastest Qwen3.8-Flash-Next Coding Agents on 4xH200

When optimized using `dstack`'s [presets](../../docs/concepts/presets.md), 4xH200 can serve 16 concurrent coding agents, with roughly 3x lower latency than the available providers. By a coding agent we mean one session of a tool like Claude Code: a multi-turn conversation with its own context of 100–150k tokens, which pauses between turns while it runs tools or waits for the user and sometimes spawns subagents.

<img src="https://dstack.ai/static-assets/static-assets/images/dstack-qwen-38-flash-next-jarvis.png" width="630" />

This work was made possible through the generous support of our partners at [Jarvislabs](https://jarvislabs.ai), who provided access to the compute.

<!-- more -->

Comparing our engine’s performance with Alibaba’s serving in [OpenRouter](https://openrouter.ai/qwen/qwen3.8-flash#performance) we get roughly 3x lower latency and about 2x higher output speed per user, at both the median and p99, as shown in the charts below. Alibaba runs two endpoints there; we compare against the faster one, using OpenRouter's own figures for the week of 6 to 13 October 2026.

=== "Output speed per user"
    <img src="https://dstack.ai/static-assets/static-assets/images/qwen38-flash-next-coding-agents-fig-1.png" width="750" />

=== "Time to first token"
    <img src="https://dstack.ai/static-assets/static-assets/images/qwen38-flash-next-coding-agents-fig-2.png" width="750" />

=== "Request latency"
    <img src="https://dstack.ai/static-assets/static-assets/images/qwen38-flash-next-coding-agents-fig-3.png" width="750" />

> Alibaba is the only provider that publishes per-request latency and throughput for this model, so it is the only endpoint we can compare against. Others serve Flash-Next, including Featherless, TensorX, FlexAI and Lyceum, but none publish performance percentiles.

## Purpose

We want to serve the fastest Qwen3.8-Flash-Next coding agents on a single 4xH200 Jarvislabs node and see how far the engine can be optimized beyond the SGLang cookbook recipe.

We also want to know how many such coding agents this node can serve. This has to be measured because the usual metrics, requests per second or tokens per second, do not answer it.

We chose a single 4xH200 node for two reasons. First, it fits the workload: Qwen3.8-Flash-Next-FP8 is 173 GB of weights, and 4 × 141 GB of HBM leaves enough room to hold several concurrent agents with their own 100–150k-token contexts, which is the input length a coding agent actually sends. Second, the SGLang cookbook publishes a recipe for exactly this configuration, which gives us a credible baseline to measure against, and shows that 4xH200 is a common hardware to serve the model rather than one chosen because it is easy to beat.

## Setup

### Hardware

In our setup, the SMG router and SGLang inference backend are separated. The SMG router is served in a CPU machine. 4xH200 is the inference worker and 8vCPU is the router. Both inference worker and router are in the same private network.

* Inference worker: Jarvislabs 4xH200, 112 vCPU, 1,200 GB RAM, 1,000 GB SSD
* Router: Jarvislabs CPU node, 8 vCPU, 32 GB RAM, 1,000 GB SSD

### Software

* Orchestration: `dstack`
* Optimization: `dstack` presets with model: Claude Opus 5

## Methodology

We used `dstack` [presets](../../docs/concepts/presets.md), an agent-based inference optimization toolkit, to find the fastest configuration for serving Qwen3.8-Flash-Next coding agents.

### Preset configuration

`dstack` presets use a locally installed Codex or Claude CLI as the optimization agent. We supplied a preset configuration that defines the model, the workload, the concurrency, the number of trials and the constraints: a 1M-token context and a median TTFT of at most 1.5 s. Presets then provide the agent with a harness for running optimization trials, benchmarking candidate configurations, and verifying the selected configuration as a deployable service. They also support chained sessions, allowing later optimization runs to inherit from previous trial records.

### Fast and full phases

We divided the optimization process into two phases based on time spent on benchmarks, because GPU time is limited. In the fast-feedback phase, we shaped the workload like one agent turn: 108k input tokens with a 97.2k shared prefix and 800 output tokens, one request per agent, all sent at once. Each benchmark run took 33 to 70 seconds, so the agent could quickly find and discard optimization changes.

In the full-replay phase, the workload was SemiAnalysis's AgentX benchmark, which we explicitly instructed the preset agent to use. It replays recorded Claude Code sessions with their growing context, the pauses between turns, and the subagents that fire several requests at once. Each benchmark run took 90 minutes. Chaining the preset sessions carried all the optimization changes from the fast-feedback phase into the full-replay phase, so the expensive runs were spent only on what real traffic could reveal.

### Baseline

SemiAnalysis's published figures for the SGLang cookbook recipe come from an earlier SGLang build, so they cannot be compared directly. To verify whether `dstack` presets improved on the baseline, we ran SemiAnalysis's exact benchmark on the SGLang build the preset used. The only difference between the two runs is the engine configuration.

## Results

Across four sessions of the fast-feedback phase, the agent raised throughput 29% over the SGLang cookbook baseline (1,088 to 1,407 tok/s), but no session met the 1.5s TTFT constraint.

The largest single win in this phase was not a setting but a patch. The agent profiled the engine, changed the source code and measured the result. The patch raised throughput by 16% (1,128 to 1,311 tok/s). It increases the prefill workspace of the QSA indexer, which picks the tokens each query attends to in the model's sparse attention, from 128 MiB to 3 GiB, so long prefill chunks are no longer split into many small pieces.

TTFT significantly fell only when we lowered the number of agents, reaching 2.5s at 16 agents in the first trial of session 4. The next two trials of session 4 improved neither TTFT nor throughput. At this point we decided to switch to the full-replay phase.

<img src="https://dstack.ai/static-assets/static-assets/images/qwen38-flash-next-coding-agents-fig-4.png" width="750" />

We started the full-replay phase with 16 agents because that is where the TTFT constraint had come closest in the fast-feedback phase. The TTFT constraint was met from the very first trial of this phase, 520ms against the 1.5s constraint. With TTFT no longer a constraint, the agent worked on throughput. It raised the throughput by 8% (669 to 720 tok/s) while TTFT improved further to 504ms.

<img src="https://dstack.ai/static-assets/static-assets/images/qwen38-flash-next-coding-agents-fig-5.png" width="750" />

Now the question is whether our methodology actually produced a configuration better than the SGLang cookbook recipe. To answer it, we explicitly asked the preset agent to run SemiAnalysis's benchmark script unchanged on our own node, using the same four H200s, the same SGLang build, the same AgentX replay at 16 agents for 3600 s, and the same pinned speculative acceptance of 2.32.

Our optimized configuration gives 13% higher throughput (628 to 708 tok/s), 37% lower TTFT at the median (793 to 502 ms) and 43% lower at p99 (5.2 to 2.9 s), and 9% lower inter-token latency at the median (7.61 to 6.91 ms) and 74% lower at p99 (83.6 to 21.6 ms). End-to-end request latency is 24% lower at the median and 40% lower at p99. The tails are better throughout, which suggests a steadier service.

So yes, the methodology worked. The preset's configuration beats the SGLang cookbook recipe with the AgentX benchmark on every metric under identical conditions, and it is more than 3 times faster than Alibaba's serving in OpenRouter.

=== "Output throughput"
    <img src="https://dstack.ai/static-assets/static-assets/images/qwen38-flash-next-coding-agents-fig-6.png" width="750" />

=== "Inter-token latency"
    <img src="https://dstack.ai/static-assets/static-assets/images/qwen38-flash-next-coding-agents-fig-7.png" width="750" />

=== "Request latency"
    <img src="https://dstack.ai/static-assets/static-assets/images/qwen38-flash-next-coding-agents-fig-8.png" width="750" />

=== "Time to first token"
    <img src="https://dstack.ai/static-assets/static-assets/images/qwen38-flash-next-coding-agents-fig-9.png" width="750" />

Since TTFT of 502 ms leaves a wide margin under the 1.5 s constraint, we checked whether the node could carry more agents. At 32 agents throughput fell to 580 tok/s and TTFT rose to 848 ms at the median and 34 s at p99, against 502 ms and 2.9 s at 16. So with 16 agents this setup gives the best performance.

## Conclusion

On a single 4xH200 node, the optimized configuration serves 16 coding agents with 13% more throughput and 37% lower TTFT than the SGLang cookbook recipe measured on the same node, and roughly 3x lower latency than the providers serving this model publicly today.

### Optimizing beyond the baseline

The answer to the first question is that the cookbook recipe is not the end: we found room beyond it in both phases, 29% more throughput on the fast-feedback workload and 13% on the full replay, from both engine settings and patches to SGLang's source code. A recipe is written for a generic deployment, while every real deployment has its own traffic shape, concurrency and latency target.

### Count agents, not requests

The answer to the second question is 16 agents, and it had to be measured, because requests per second and tokens per second say nothing about how many coding agents a node can serve. An agent is not a request: it holds its context for the whole session, idles between turns, and occasionally spawns subagents. In the full replay, 16 agents produced about 5 concurrent requests on average and 20 at peak, so when estimating agent serving capacity, plan on the number of agents rather than requests.

### Fast-feedback phase

Splitting the optimization process into two phases paid off: almost all the winning changes came from the fast-feedback phase, and the ones that did not work were discarded within minutes instead of 90 minutes.

## Limitations

1. The fast-feedback workload could be designed better. Its requests are independent, not sessions: they arrive and finish together, so the engine never has to hold many long contexts while they sit idle waiting for their next turn. Running out of room for those waiting contexts is exactly what limited us to 32 agents, and since the fast-feedback benchmark cannot show it, the agent never worked on it. A better fast workload would keep the shape of a session while still finishing in under a minute.
2. Real traffic shape but generated text. The full-replay traces keep the real session structure, token counts and think gaps, but the prompt tokens are generated. Anything that depends on what the text says can differ from production, for example how many tokens speculative decoding guesses correctly.
3. We capped each session at three trials for budget reasons. In several sessions the agent still had untried ideas when the session ended, so more trials or more sessions would likely find more improvements.

## Deploy the optimized preset to your hardware

The exported service configuration defines the exact resources: 4xH200 for the inference worker and 8 vCPU for the router. The fleet only needs the [Jarvislabs](../../docs/concepts/backends.md#jarvislabs) backend, cluster placement, and a region where both are available:

<div editor-title="fleet.dstack.yml">

```yaml
type: fleet
name: jarvislabs-h200

# Provision instances only on Jarvislabs
backends: [jarvislabs]
# The region with both 4xH200 and 8 vCPU instances
regions: [india-noida-01]
# The worker and the router share a private network
placement: cluster

# Provision instances when the service is submitted
nodes: 0..2

resources:
  gpu: 0..4
```

</div>

Pass the fleet configuration to `dstack apply`:

<div class="termy">

```shell
$ dstack apply -f fleet.dstack.yml
```

</div>

If you have your own hardware, create an [SSH fleet](../../docs/concepts/fleets.md) instead, with a 4xH200 node (112 vCPU, 1,200 GB RAM, 1,000 GB SSD) and a CPU node (8 vCPU, 32 GB RAM, 1,000 GB SSD) in the same private network.

The preset is [public](https://sky.dstack.ai/presets/dstackai/qwen3-8-flash-next-h200). Pull the preset:

<div class="termy">

```shell
$ dstack preset pull dstackai/qwen3-8-flash-next-h200
```

</div>

Export the preset to create a service configuration:

<div class="termy">

```shell
$ dstack preset export dstackai/qwen3-8-flash-next-h200 -f qwen3-8-flash-next-h200.dstack.yml
```

</div>

Apply the service configuration to deploy the optimized preset on your hardware:

<div class="termy">

```shell
$ dstack apply -f qwen3-8-flash-next-h200.dstack.yml
```

</div>

## Thanks to our partners

### Jarvislabs

[Jarvislabs](https://jarvislabs.ai) is the primary sponsor of this work, and we are sincerely grateful for their compute and support.

If you'd like to use high quality on-demand compute with NVIDIA GPUs, we recommend going with [Jarvislabs](https://jarvislabs.ai). It’s possible to provision compute on Jarvislabs and orchestrate training and inference entirely via `dstack`.

If you'd like to use a managed model API directly, Jarvislabs [Model APIs](https://jarvislabs.ai/products/models) serve frontier open-source models through an OpenAI-compatible API.
