---
title: "Benchmarking Prefill–Decode: fixed 1:3 as a strong default"
date: 2025-09-25
description: "TBA"  
slug: benchmarking-pd-ratios
image: https://dstack.ai/static-assets/static-assets/images/benchmarking-pd-ratios.png
categories:
  - Benchmarks
---

# Benchmarking Prefill–Decode: fixed 1:3 as a strong default

As demand for low-latency LLM inference grows, squeezing more useful work out of every GPU minute is critical.
This benchmark evaluates how the Prefill–Decode worker disaggregatioh ratio affects performance across workload profiles and concurrency levels,
and assess if dynamic ratio adjustment adds value.

<img src="https://dstack.ai/static-assets/static-assets/images/benchmarking-pd-ratios.png" width="630" />

<!-- more -->

## Introduction

### What is Prefill–Decode disaggregation?

DistServe ([Zhong et al., 2024 :material-arrow-top-right-thin:{ .external }](https://arxiv.org/pdf/2401.09670){:target="_blank"}) proposes prefill–decode disaggregation, separating the two phases of inference across dedicated workers.
Prefill can be heavily batched—prompt tokens are processed in parallel—so it is compute-intensive. Decode is intrinsically sequential—one token per iteration with full KV-cache access—so it is memory- and bandwidth-intensive. Disaggregating these phases reduces cross-phase interference, allowing hardware to be provisioned for the dominant bottleneck and improving end-to-end service performance.

### What is the Prefill–Decode ratio?

The optimal split between prefill and decode workers depends on service-level objectives (SLOs) and workload shape. DistServe shows that for input sequence length (ISL) = 512 and output sequence length (OSL) = 64, "2 prefill to 1 decode" meets both TTFT and TPOT targets. Beyond this illustrative case, however, DistServe does not systematically explore other Prefill–Decode ratios.

!!! info "Reasoning model example"
    In the DeepSeek deployment ([LMSYS, 2025 :material-arrow-top-right-thin:{ .external }](https://lmsys.org/blog/2025-05-05-large-scale-ep){:target="_blank"}), 3 nodes were allocated to prefill and 9 to decode. The decode-heavy split reflects reasoning workloads, where chains of thought push output lengths high. Allocating more capacity to decode reduces inter-token latency and keeps long responses streaming smoothly.

### Dynamic ratio adjustment

Dynamic allocation adjusts the split between prefill and decode workers at runtime. NVIDIA’s [SLA-based planner :material-arrow-top-right-thin:{ .external }](https://docs.nvidia.com/dynamo/latest/architecture/sla_planner.html){:target="_blank"}
estimates the workers needed to meet TTFT and ITL targets, while the [Load-based planner :material-arrow-top-right-thin:{ .external }](https://docs.nvidia.com/dynamo/latest/architecture/load_planner.html){:target="_blank"}
reallocates workers using KV-cache and queue signals. These planners describe how to move capacity between phases, but they do not prescribe a specific Prefill–Decode ratio.

## Benchmark purpose

Prior art points to different “best” ratios depending on workload: DistServe’s 2:1 for short outputs, the SGLang DeepSeek example’s 1:3 for long outputs, and dynamic planners that adapt the split in real time. Building on these insights, this benchmark evaluates how the Prefill–Decode worker ratio affects performance across workload profiles and concurrency levels. 

We measure TTFT, ITL, and throughput to understand how allocation choices influence both latency and efficiency—and to assess when dynamic ratio adjustment adds value versus when a fixed ratio suffices for a known workload.

??? info "Why these metrics matter"

    * **TTFT** (Time to First Token) captures perceived responsiveness—crucial for interactive experiences (e.g., support bots, code assistants).
    * **ITL** (inter-token latency) captures streaming smoothness—critical for long, reasoning-style outputs.
    * **Throughput** (tokens/sec) reflects cost efficiency. Prefill-heavy tasks (e.g., summarization of long docs) stress prefill; reasoning tasks stress decode. Maintaining high throughput ensures the under-stressed phase doesn’t leave GPUs idle.

## Methodology

We ran a single-node study on 8xH200 GPUs, varying the number of prefill and decode workers to examine how the split shapes performance. We compared three prefill-decode ratios—3:1, 2:2, 1:3 both lower and higher request concurrency for three workload profiles:

* **Prefill-heavy** (ISL > OSL) — e.g., summarization: long inputs, short outputs.
* **Decode-heavy** (ISL < OSL) — e.g., reasoning: short inputs, long chains of thought.
* **Balanced** (ISL ≈ OSL) — e.g., translation, paraphrasing.

Lower concurrency highlights intrinsic trade-offs (prefill-leaning improves TTFT; decode-leaning improves ITL and throughput). Higher concurrency reveals the true bottleneck. In real deployments, success is meeting TTFT/ITL SLOs and sustaining throughput for cost efficiency, so we evaluate both.

> A single-node design isolates the question at hand—does adjusting the prefill/decode split improve performance? If a benefit doesn’t manifest on one node, scaling out will typically amplify the same dynamics rather than change them.

## Benchmark setup

* **GPU**: NVIDIA 8xH200 (SXM5)
* **CPU**: Intel Xeon Platinum 8468  
* **Model**: `openai/gpt-oss-120b`  
* **Backend**: SGLang

For full steps and raw data, see the [GitHub repo :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/benchmarks/tree/main/comparison/pd_ratio){:target="_blank"}.

## Finding 1: Prefill-heavy workloads

At lower concurrency, 1:3 yields the best ITL and throughput but the worst TTFT. Ratios 3:1 and 2:2 improve TTFT because more prefill capacity clears prompts faster. However, with 3:1, a single decode worker becomes a chokepoint—queues build up, ITL rises, and overall throughput drops.

At higher concurrency, 1:3 wins across all metrics. Because TTFT = prefill time + waiting at decode + time to first token, ample decode capacity trims the waiting component, improving TTFT even on prefill-heavy inputs.

In practice, summarization rarely has tight TTFT SLOs—users expect some delay after uploading long documents. Throughput and ITL dominate cost and experience, making 1:3 the recommended split for prefill-heavy workloads at both low and high concurrency.

*TBA: Fig-1: ISL 2048, OSL 128, concurrency 32*

> Metrics are normalized per chart: the best value for each metric is 100%; others are percentages of that maximum. Lower is better for ITL/TTFT; higher is better for Throughput.

*TBA: Fig-2: ISL 2048, OSL 128, concurrency 128*

## Finding 2: Decode-heavy workloads

As with prefill-heavy cases, at lower concurrency a 1:3 split delivers the best ITL and throughput, at the cost of higher TTFT. Ratios 3:1 and 2:2 improve TTFT but degrade streaming smoothness and throughput.

At higher concurrency, 1:3 again leads across all metrics.

For reasoning tasks, ITL is usually the tightest SLO—smooth, uninterrupted token streaming drives user experience. We recommend 1:3 for decode-heavy workloads at both low and high concurrency.

*TBA: Fig-3: ISL 128, OSL 2048, concurrency 32*

> Metrics normalized as above. Lower is better for ITL/TTFT; higher is better for Throughput.

*TBA: Fig-4: ISL 128, OSL 2048, concurrency 128*

## Finding 3: Balanced workloads

At lower concurrency, 1:1 provides the most balanced profile: better TTFT than the other ratios, with only modest trade-offs in ITL and throughput versus 1:3.

At higher concurrency, 1:3 regains the lead across metrics, while 1:1 sees TTFT degrade as decode pressure grows.

Since 1:1 becomes limiting under load, 1:3 is the safer default for balanced workloads—1:1 can offer slightly lower TTFT at light load, but 1:3 scales better and sustains higher throughput.

*TBA: Fig-5: ISL 2048, OSL 2048, concurrency 32*

> Metrics normalized as above. Lower is better for ITL/TTFT; higher is better for Throughput.

*TBA: Fig-6: ISL 2048, OSL 2048, concurrency 128*

## Conclusion

This study examined how the prefill/decode split shapes performance across workload profiles and load levels, and when dynamic adjustment is beneficial.

1. A decode-leaning default performs robustly. Across profiles and loads, 1:3 consistently offered the strongest ITL and throughput, while keeping TTFT competitive when concurrency rises. For many known workload mixes, this reduces the need for dynamic rebalancing.
2. Resilience under surges. The 1:3 split scales gracefully with concurrency, absorbing bursts without resorting to complex runtime adjustments.
3. TTFT in context. 1:3 can show higher TTFT at low concurrency, but real-world expectations matter. Summarization users anticipate a delay after long uploads; reasoning users value smooth streaming most. For interactive chat with tight TTFT SLOs, techniques such as prefix caching and cache-aware routing can reduce prefill work and lower TTFT—often without changing the prefill/decode split.

> Taken together, these results suggest that while dynamic planners (e.g., SLA- and load-based) provide a powerful framework to adapt capacity, in many production scenarios a simple, decode-leaning 1:3 baseline plus conventional autoscaling delivers excellent outcomes with less operational complexity.

## Limitations

This evaluation uses SGLang’s implementation of Prefill–Decode disaggregation. To strengthen generality, repeating the study with vLLM’s implementation would be valuable.

## References

* [DistServe :material-arrow-top-right-thin:{ .external }](https://arxiv.org/pdf/2401.09670){:target="_blank"}
* [DeepSeek deployment on 96 H100 GPUs :material-arrow-top-right-thin:{ .external }](https://lmsys.org/blog/2025-05-05-large-scale-ep/){:target="_blank"}
* [Dynamo disaggregated serving :material-arrow-top-right-thin:{ .external }](https://docs.nvidia.com/dynamo/latest/architecture/disagg_serving.html#){:target="_blank"}
* [SGLang PD disaggregation :material-arrow-top-right-thin:{ .external }](https://docs.sglang.ai/advanced_features/pd_disaggregation.html){:target="_blank"}
* [vLLM disaggregated prefilling :material-arrow-top-right-thin:{ .external }](https://docs.vllm.ai/en/v0.9.2/features/disagg_prefill.html){:target="_blank"}

!!! info "What's next?"

    * **KV-cache–aware routing & prefix caching with PD**: Quantify how cache-aware routing and prefix caching, combined with PD, reduce redundant prefill compute and improve TTFT.
    * **PD with model parallelism**: Extend beyond tensor parallelism to assess how additional forms of model parallelism interact with PD and affect latency/throughput trade-offs.
