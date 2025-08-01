---
title: "DeepSeek R1 inference performance: MI300X vs. H200"
date: 2025-03-18
description: "TBA"
slug: h200-mi300x-deepskeek-benchmark
image: https://dstack.ai/static-assets/static-assets/images/h200-mi300x-deepskeek-benchmark-v2.png
categories:
  - Benchmarks
---

# DeepSeek R1 inference performance: MI300X vs. H200

DeepSeek-R1, with its innovative architecture combining Multi-head Latent Attention (MLA) and DeepSeekMoE, presents
unique challenges for inference workloads. As a reasoning-focused model, it generates intermediate chain-of-thought
outputs, placing significant demands on memory capacity and bandwidth.

In this benchmark, we evaluate the performance of three inference backends—SGLang, vLLM, and TensorRT-LLM—on two hardware
configurations: 8x NVIDIA H200 and 8x AMD MI300X. Our goal is to compare throughput, latency, and overall efficiency to
determine the optimal backend and hardware pairing for DeepSeek-R1's demanding requirements.

<img src="https://dstack.ai/static-assets/static-assets/images/h200-mi300x-deepskeek-benchmark-v2.png" width="630"/>

This benchmark was made possible through the generous support of our partners at
[Vultr :material-arrow-top-right-thin:{ .external }](https://www.vultr.com/){:target="_blank"} and 
[Lambda :material-arrow-top-right-thin:{ .external }](https://lambdalabs.com/){:target="_blank"},
who provided access to the necessary hardware.

<!-- more -->

## Benchmark setup

### Hardware configurations

1. AMD 8xMI300x
    * 2x Intel Xeon Platinum 8468, 48C/96T, 16GT/s, 105M Cache (350W)
    * 8x AMD MI300x GPU, 192GB, 750W
	* 32x 64GB DDR5, 4800MT/s
2. NVIDIA 8xH200 SXM5
    * 2x Intel Xeon Platinum 8570, 56C/112T, 20GT/s, 300M Cache (350W)
    * 8x NVIDIA H200 SXM5 GPU, 141GB, 700W
    * 32x 64GB DDR5, 5600MT/s

### Benchmark methodology

**Online inference**

We utilized SGLang's [`Deepseek-R1/bench_serving.py` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/benchmarks/tree/main/Deepseek-R1/bench_serving.py){:target="_blank"} 
script, modified to incorporate TensorRT-LLM. 

Tests were conducted across multiple request concurrencies and output token lengths, with input token length fixed at 3200.

| Request Concurrencies  | Output Token Lengths | Prefix-Cached  |
|------------------------|----------------------|----------------|
| 4,8,16,...,128         | 800                  | No             |
| 128                    | 1600, 3200, 6400     | No             |
| 128                    | 800                  | Yes            |

To test prefix caching ability, about 62.5% of each ~3200-token prompt (i.e., 2000 out of 3200 tokens) is a repeated prefix across multiple requests.

**Offline inference**

For offline inference, we used vLLM’s [`benchmark_throughput.py` :material-arrow-top-right-thin:{ .external }](https://github.com/vllm-project/vllm/blob/main/benchmarks/benchmark_throughput.py){:target="_blank"},
modified for SGLang. TensorRT-LLM was tested using a custom 
[`benchmark_throughput_trt.py` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/benchmarks/blob/deepseek-r1-benchmark/Deepseek-R1/benchmark_throughput_trt.py){:target="_blank"}. 
The benchmark examined performance across various batch sizes and output token lengths.

| Batch Sizes        | Output Token Lengths |
|--------------------|----------------------|
| 32,64,128,...,1024 | 800                  |
| 256, 512, 1024     | 1600                 |
| 256, 512, 1024     | 3200                 |

## Key observations

### Throughput and End-to-End Latency

**NVIDIA H200 performance**

* TensorRT-LLM outperformed both vLLM and SGLang, achieving the highest online throughput of 4176 tokens/s on H200.
* At concurrencies below 128, vLLM led in online throughput and end-to-end latency.
* In offline scenarios, H200 achieved the highest overall throughput of 6311 tokens/s with SGLang.

<img src="https://github.com/dstackai/benchmarks/raw/deepseek-r1-benchmark/Deepseek-R1/images/online_throughput_vs_latency.png" />

**AMD MI300X performance**

* vLLM outperformed SGLang in both online and offline throughput and end-to-end latency.
* MI300X with vLLM achieved the highest overall throughput of 4574 tokens/s in online scenarios.
* At request concurrencies below 32, SGLang outperformed vLLM in online throughput and latency.

<img src="https://github.com/dstackai/benchmarks/raw/deepseek-r1-benchmark/Deepseek-R1/images/offline_throughput_vs_latency.png" />

While MI300X's larger memory capacity and higher bandwidth should theoretically enable higher throughput at larger batch
sizes, the results suggest that inference backends for MI300X may require further optimization to fully leverage its
architectural advantages.

### Throughput and Latency vs. Output Token Length

**NVIDIA H200 performance**

* SGLang delivered slightly higher throughput and better latency as output token length increased in online scenarios.
* In offline scenarios, SGLang with H200 outperformed MI300X as output token length increased.

=== "Throughput"
    <img src="https://github.com/dstackai/benchmarks/raw/deepseek-r1-benchmark/Deepseek-R1/images/online-throughput-vs-output.png" />

=== "Latency"
    <img src="https://github.com/dstackai/benchmarks/raw/deepseek-r1-benchmark/Deepseek-R1/images/online-latency-vs-output.png" />

**AMD MI300X performance**

vLLM maintained the lead in both online and offline scenarios as output token length increased.

=== "Throughput"
    <img src="https://github.com/dstackai/benchmarks/raw/deepseek-r1-benchmark/Deepseek-R1/images/offline-throughput-vs-output-256.png" />

=== "Latency"
    <img src="https://github.com/dstackai/benchmarks/raw/deepseek-r1-benchmark/Deepseek-R1/images/offline-latency-vs-output-length-256.png" />

### Time to First Token (TTFT)

**NVIDIA H200 performance**

TensorRT-LLM maintained the lowest and most consistent TTFT up to concurrency 64.

<img src="https://github.com/dstackai/benchmarks/raw/deepseek-r1-benchmark/Deepseek-R1/images/ttft-vs-concurrency.png" />

**AMD MI300X performance**

vLLM achieved the lowest TTFT at concurrency 128. Below 128, vLLM and SGLang had similar TTFT.

TTFT, being compute-intensive, highlights H200's advantage, aligning with [SemiAnalysis’s MI300X vs. H200 TFLOPS benchmark :material-arrow-top-right-thin:{ .external }](https://semianalysis.com/2024/12/22/mi300x-vs-h100-vs-h200-benchmark-part-1-training/){:target="_blank"}.
However, at 128 concurrent requests, MI300X's memory capacity and bandwidth advantages become evident.

### Time Per Output Token (TPOT)

**NVIDIA H200 performance**

vLLM maintained the lowest TPOT across all request concurrencies.

<img src="https://github.com/dstackai/benchmarks/raw/deepseek-r1-benchmark/Deepseek-R1/images/tpot-vs-concurrency.png" />

**AMD MI300X performance**

SGLang delivered the lowest TPOT up to concurrency 32. Beyond that, vLLM took the lead.

Given that TPOT is memory-bound, MI300X should have a stronger advantage with further optimizations.

### TTFT vs. Output Token Length

**NVIDIA H200 performance**

* SGLang demonstrated stable TTFT across increasing output token lengths.
* vLLM and TensorRT-LLM showed significant increases in TTFT as output token length grew, likely due to KV cache memory pressure.

<img src="https://github.com/dstackai/benchmarks/raw/deepseek-r1-benchmark/Deepseek-R1/images/ttft-vs-output-length.png" />

**AMD MI300X performance**

Both vLLM and SGLang demonstrated stable TTFT across increasing output token lengths, with vLLM maintaining lower TTFT.

<img src="https://github.com/dstackai/benchmarks/raw/deepseek-r1-benchmark/Deepseek-R1/images/ttft-vs-output-length-no-h200-vllm.png" />

### TPOT vs. Output Token Length

**NVIDIA H200 performance**

SGLang and TensorRT-LLM demonstrated stable TPOT across increasing output token lengths.

<img src="https://github.com/dstackai/benchmarks/raw/deepseek-r1-benchmark/Deepseek-R1/images/tpot-vs-output-length.png" />

vLLM maintained the lowest TPOT up to 3200 tokens but showed a sudden increase at 6400 tokens, likely due to memory pressure.

**AMD MI300X performance**

Both SGLang and vLLM demonstrated stable TPOT across increasing output token lengths, with vLLM maintaining the lowest TPOT.

### Prefix caching

**NVIDIA H200 performance**

vLLM outperformed SGLang in online throughput, TTFT, and end-to-end latency with prefix caching enabled. However, vLLM's
TPOT increased after prefix caching, which requires further investigation.

=== "Throughput"
    <img src="https://github.com/dstackai/benchmarks/raw/deepseek-r1-benchmark/Deepseek-R1/images/prefix-cache-throughput-comparison.png" />
=== "TTFT"
    <img src="https://github.com/dstackai/benchmarks/raw/deepseek-r1-benchmark/Deepseek-R1/images/prefix-cache-ttft-comparison.png" />
=== "TPOT"
    <img src="https://github.com/dstackai/benchmarks/raw/deepseek-r1-benchmark/Deepseek-R1/images/prefix-cache-tpot-comparison.png" />
=== "Latency"
    <img src="https://github.com/dstackai/benchmarks/raw/deepseek-r1-benchmark/Deepseek-R1/images/prefix-cache-end-to-end-latency-comparison.png" />

## Limitations

1. The offline benchmark results for TensorRT-LLM were obtained using the DeepSeek-R1 model engine built from the
   [`deepseek` branch :material-arrow-top-right-thin:{ .external }](https://github.com/NVIDIA/TensorRT-LLM/tree/deepseek){:target="_blank"}.
   However, the TensorRT-LLM team recommends using the TorchFlow-based approach for deployment.
2. The impact of dynamic batching on inference efficiency was not tested.
3. vLLM's prefix caching support for MI300X is a work in progress and can be tracked [here :material-arrow-top-right-thin:{ .external }](https://github.com/ROCm/vllm/issues/457){:target="_blank"}.
4. The inference backends are being optimized for the DeepSeek-R1 model. Given these continuous updates, the current
   results reflect only the performance tested at the time of the benchmark. Overall, performance for all backends is
   expected to improve as more optimizations are made by the backend teams.

## Source code

All source code and findings are available in
[our GitHub repo :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/benchmarks/tree/deepseek-r1-benchmark/Deepseek-R1){:target="_blank"}.

## References

* [Unlock DeepSeek-R1 Inference Performance on AMD Instinct MI300X GPU :material-arrow-top-right-thin:{ .external }](https://rocm.blogs.amd.com/artificial-intelligence/DeepSeekR1_Perf/README.html){:target="_blank"}
* [Deploy DeepSeek-R1 671B on 8x NVIDIA H200 with SGLang :material-arrow-top-right-thin:{ .external }](https://datacrunch.io/blog/deploy-deepseek-r1-on-8x-nvidia-h200){:target="_blank"}
* [vLLM Prefix Caching :material-arrow-top-right-thin:{ .external }](https://docs.vllm.ai/en/latest/design/automatic_prefix_caching.html#design-automatic-prefix-caching){:target="_blank"}
* [SgLang Prefix Caching :material-arrow-top-right-thin:{ .external }](https://lmsys.org/blog/2024-01-17-sglang/){:target="_blank"}

## Acknowledgments

### Vultr

[Vultr :material-arrow-top-right-thin:{ .external }](https://www.vultr.com/){:target="_blank"} provided access to 8x AMD MI300X GPUs. We are truly thankful for their support.

If you're looking for top-tier bare metal compute with AMD GPUs, we highly recommend Vultr. With `dstack`, provisioning
and accessing compute via `dstack` is seamless and straightforward.

### Lambda

[Lambda :material-arrow-top-right-thin:{ .external }](https://lambdalabs.com/){:target="_blank"} provided access to 8x
NVIDIA H200 GPUs. We are truly thankful for their support

Both Vultr and Lambda are natively supported and can be seamlessly integrated with `dstack`. 
