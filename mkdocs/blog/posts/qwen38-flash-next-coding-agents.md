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

Comparing our engine’s performance with Alibaba’s serving in [OpenRouter](https://openrouter.ai/qwen/qwen3.8-flash#performance) we get roughly 3x lower latency and about 2.5x higher output speed per user, at both the median and p99, as shown in the charts below. Alibaba runs two endpoints there; we compare against the faster one, using OpenRouter's own figures for the week of 6 to 13 October 2026.

=== "Output speed per user"
    <img src="https://dstack.ai/static-assets/static-assets/images/qwen38-flash-next-coding-agents-fig-1.png" width="750" />

=== "Time to first token"
    <img src="https://dstack.ai/static-assets/static-assets/images/qwen38-flash-next-coding-agents-fig-2.png" width="750" />

=== "Request latency"
    <img src="https://dstack.ai/static-assets/static-assets/images/qwen38-flash-next-coding-agents-fig-3.png" width="750" />

## Purpose

We want to serve the fastest Qwen3.8-Flash-Next coding agents on a single 4xH200 Jarvislabs node and see how far the engine can be optimized beyond SGLang Cookbook.

We also want to know how many such coding agents this node can serve. This has to be measured because the usual metrics, request per second or tokens per second do not answer it.

We chose a single 4xH200 node for two reasons. First, it fits the workload: Qwen3.8-Flash-Next-FP8 is 173 GB of weights, and 4 × 141 GB of HBM leaves enough room to hold several concurrent agents with their own 100–150k-token contexts, which is the input length a coding agent actually sends. Second, the SGLang cookbook publishes a recipe for exactly this configuration, which gives us a credible baseline to measure against, and shows that 4xH200 is a common hardware to serve the model rather than one chosen because it is easy to beat.

## Setup

### Hardware

In our setup, the SMG router and SGLang inference backend are separated. The SMG router is served in a CPU machine. 4xH200 is the inference worker and 8vCPU is the router. Both inference worker and router are in the same private network.

* Inference worker: Jarvislabs 4xH200, 112 vCPU, 1,200 GB RAM, 1,000 GB SSD
* Router: Jarvislabs CPU node, 8 vCPU, 32 GB RAM, 1,000 GB SSD

### Software

* Orchestration: `dstack`
* Optimization: `dstack` presets with model: Claude Opus 5

### Methodology

We used `dstack` [presets](../../docs/concepts/presets.md), an agent-based inference optimization toolkit, to find the fastest configuration for serving Qwen3.8-Flash-Next coding agents on a single 4xH200 Jarvislabs node plus a CPU node for a router in the same VPC.

`dstack` presets use a locally installed Codex or Claude CLI as the optimization agent with its own optimization harness. We supplied a preset configuration that defines the model, synthetic workload (`input_tokens`, `output_tokens`, `shared_prefix_tokens`) or dataset, constraints (`min_context_length`, `max_ttft`), concurrency and number of trials. Presets then provide the agent with a harness for running optimization trials, submitting `dstack` runs, benchmarking candidate configurations, and finally verifying the selected configuration as a deployable service. They also support chained sessions, allowing later optimization runs to inherit from previous trial records.

For our purpose, we divided the optimization process into two phases based on time spent on benchmarks.

The first phase is the fast-feedback phase. Here we shaped the workload like one agent turn: 108k input tokens of which 97.2k are a shared prefix, 800 output tokens, with all requests sent at once. The purpose of this phase is to give the agent fast feedback through a quick benchmark. In this phase, each benchmark run completes in 33 to 70 seconds, so the agent can try the changes and know their effect faster.

The second is the full-replay phase, where the workload is the real agentic sessions instead of the burst of requests we used in the fast-feedback phase. We explicitly instructed the preset agent to use SemiAnalysis's AgentX benchmark. It is built from recorded Claude Code sessions. Each session is a multi-turn conversation: a first short prompt, then turns that grow as the agent reads files and accumulates context, with the gaps where the user was thinking or a tool was running preserved exactly as they happened, and the places where the agent spawned subagents and issued several requests at once. Each benchmark run takes 90 minutes, so compared with the fast-feedback phase the agent gets its feedback far more slowly, and the optimization takes much longer.

We split the work this way because GPU time is limited. The fast-feedback phase let the agent find and discard optimization changes in under a minute, so by the time we moved to the full-replay phase the engine was already carrying everything the quick benchmark could establish, and the expensive runs were spent only on what real traffic could reveal. Chaining multiple preset optimization sessions, we inherited all the optimization changes from the fast-feedback phase into the full-replay phase.

To verify whether `dstack` presets improved on the baseline, we explicitly instructed the preset agent to use SemiAnalysis's benchmark script, because it runs the SGLang cookbook recipe with the AgentX benchmark. We did not compare against SemiAnalysis's published figures, because those were measured on their own cluster with an earlier SGLang build, so we took only the methodology from them and ran everything ourselves: the same SGLang build, the same Jarvislabs 4xH200 node, the same AgentX replay at 16 sessions for 3600 s, and the same pinned speculative acceptance of 2.32 on both sides. The only difference between the two runs is the engine configuration: the preset's optimized configuration against the cookbook recipe.

## Results

### Fast-feedback phase

Across four sessions of the fast-feedback phase, the agent raised throughput 29% over the SGLang cookbook baseline (1,088 to 1,407 tok/s), but no session met the 1.5s TTFT constraint.

The largest single win in this phase was not a setting but a patch. The agent profiled the engine, changed the source code and measured the result. The patch raised throughput by 16% (1,128 to 1,311 tok/s).

TTFT only fell when we lowered the number of agents, reaching 2.5s at 16 agents in the first trial of session 4. The next two trials of session 4 improved neither TTFT nor throughput. At this point we decided to switch to the full-replay phase.

<img src="https://dstack.ai/static-assets/static-assets/images/qwen38-flash-next-coding-agents-fig-4.png" width="750" />

### Full-replay phase

We started the full-replay phase with 16 agents because that is where the TTFT constraint had come closest in the fast-feedback phase. The TTFT constraint was met from the very first trial of this phase, 520ms against the 1.5s constraint. With TTFT no longer a constraint, the agent worked on throughput. It raised the throughput by 8% (669 to 720 tok/s) while TTFT improved further to 504ms.

<img src="https://dstack.ai/static-assets/static-assets/images/qwen38-flash-next-coding-agents-fig-5.png" width="750" />

### Comparison with the SGLang cookbook recipe

Now the question is whether our methodology actually produced a configuration better than the SGLang cookbook recipe. To answer it, we explicitly asked the preset agent to run SemiAnalysis's benchmark script unchanged on our own node, using the same four H200s, the same SGLang build, the same AgentX replay at 16 agents for 3600 s, and the same pinned speculative acceptance of 2.32.

Our optimized configuration gives 13% higher throughput (628 to 708 tok/s), 37% lower TTFT at the median (793 to 502 ms) and 43% lower at p99 (5.2 to 2.9 s), and 9% lower inter-token latency at the median (7.61 to 6.91 ms) and 74% lower at p99 (83.6 to 21.6 ms). End-to-end request latency is 24% lower at the median and 40% lower at p99. The tails are better throughout, which suggests a steadier service.

So yes, the methodology worked. The preset's configuration beats the SGLang cookbook recipe with the AgentX benchmark on every metric under identical conditions, and it is more than 3 times faster than the only provider serving this model publicly today.

=== "Output throughput"
    <img src="https://dstack.ai/static-assets/static-assets/images/qwen38-flash-next-coding-agents-fig-6.png" width="750" />

=== "Inter-token latency"
    <img src="https://dstack.ai/static-assets/static-assets/images/qwen38-flash-next-coding-agents-fig-7.png" width="750" />

=== "Request latency"
    <img src="https://dstack.ai/static-assets/static-assets/images/qwen38-flash-next-coding-agents-fig-8.png" width="750" />

=== "Time to first token"
    <img src="https://dstack.ai/static-assets/static-assets/images/qwen38-flash-next-coding-agents-fig-9.png" width="750" />

### More agents

Since TTFT of 502 ms leaves a wide margin under the 1.5 s constraint, we checked whether the node could carry more agents. At 32 agents throughput fell to 580 tok/s and TTFT rose to 848 ms at the median and 34 s at p99, against 502 ms and 2.9 s at 16. So with 16 agents this setup gives the best performance.

## Conclusion

On a single 4xH200 node, the optimized configuration serves 16 coding agents at 708 tok/s with 502 ms to first token, which is 13% more throughput and 37% lower TTFT than the SGLang cookbook recipe measured on the same node, and roughly 3x lower latency than the providers serving this model publicly today. So the answer to the first question is that the cookbook recipe is not the end: there is room beyond it, and we found that room in both phases, 29% over the baseline on the fast-feedback workload (1,088 to 1,407 tok/s) and 13% on the full replay. A cookbook recipe is written for a generic deployment, and every real deployment differs. The model may be the same, but the traffic shape, the concurrency and the latency target are not.

The answer to the second question is 16 agents, and it had to be measured rather than derived from requests per second and tokens per second, because both of these metrics say nothing about how many coding agents a node can serve. An agent is not a request: it holds a 100–150k-token context for its whole session, idles between turns while it runs tools or waits for the user, and occasionally spawns subagents that fire several requests at once. Our two phases show the gap directly. In the fast-feedback phase, 16 requests meant 16 requests in flight; in the full replay, the same 16 agents produced about 5 concurrent requests on average, 17 at p99 and 20 at peak.

Our methodology of splitting the optimization process into a fast-feedback phase and a full-replay phase paid off in two ways. First, almost all the winning changes came from the fast phase, and only one came from the full-replay phase. Second, the changes that did not work were discarded in the fast phase within minutes instead of spending 90 minutes in the full-replay phase.

For anyone self-hosting coding agents, three things follow. Start optimization with a fast benchmark that looks like your traffic, so changes that do not work are thrown out quickly, then move to the real workload for the rest. Do not assume the published recipe is the end, because it was written for a generic deployment that is probably not yours. And when estimating agent serving capacity, plan on the number of agents rather than requests, and measure it with a full replay.

## Limitations

1. The fast-feedback workload could be designed better. We shaped it only by request size: 108k input tokens with a 97.2k shared prefix and 800 output tokens, all sent at once. Those are independent requests, not sessions. They arrive together and finish together, so the engine never has to hold many long contexts in memory while they sit idle waiting for their next turn. Running out of room for those waiting contexts is exactly what limited us to 32 agents, and the current fast-feedback benchmark cannot show it, so the agent never worked on it. A better fast workload would keep the shape of a session, while still finishing in under a minute.
2. Real traffic shape but generated text. Even in the full-replay phase the text is not real: the traces keep the real session structure, token counts and think gaps, but the prompt tokens are generated. Anything that depends on what the text says can therefore differ from production. For example: speculative decoding guesses the next few tokens from the preceding text and keeps the guesses the model agrees with, and generated text can be easier or harder to guess than real text.
3. We capped each session at three trials. Every session ran three trials, and in several of them the agent still had untried ideas when the session ended. The cap was a conservative budget decision rather than a sign that the configuration had stopped improving, so more trials per session, or more sessions, would likely find more changes for improvement.

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

## Acknowledgments

### Jarvislabs

[Jarvislabs](https://jarvislabs.ai) is the primary sponsor of this work, and we are sincerely grateful for their compute and support.

If you'd like to use high quality on-demand compute with NVIDIA GPUs, we recommend going with [Jarvislabs](https://jarvislabs.ai). It’s possible to provision compute on Jarvislabs and orchestrate training and inference entirely via `dstack`.

If you'd like to use a managed model API directly, Jarvislabs [Model APIs](https://jarvislabs.ai/products/models) serve frontier open-source models through an OpenAI-compatible API.
