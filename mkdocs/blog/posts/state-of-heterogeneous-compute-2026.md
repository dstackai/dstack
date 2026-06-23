---
title: "The state of heterogeneous AI compute in 2026"
date: 2026-06-26
description: "How supply, software readiness, orchestration, and networking shape accelerator choices across NVIDIA, AMD, TPUs, Trainium, and specialized inference systems."
slug: state-of-heterogeneous-compute-2026
image: https://dstack.ai/static-assets/static-assets/images/state-of-heterogeneous-compute-2026.png
categories:
  - Reports
---

# The state of heterogeneous AI compute in 2026

Heterogeneous AI compute is becoming harder to ignore. The reason is practical: supply pressure, pricing, and stack readiness are making more than one accelerator path worth evaluating.

<img src="https://dstack.ai/static-assets/static-assets/images/state-of-heterogeneous-compute-2026.png" width="750"/>

This report focuses on accelerator choices behind training and inference workloads: the main patterns, the evidence behind them, how readiness differs, and why orchestration and networking determine whether capacity can be used in practice.

<!-- more -->

## Patterns

Heterogeneous compute has two dimensions: how capacity is pooled, and where execution crosses hardware boundaries. Separate pools are operationally tractable; one training run or one inference request spanning unlike stacks requires much more validation. The patterns below are roughly ordered from most practical to most experimental.

| Pattern | What it means |
| :---- | :---- |
| **Same stack, different generations** | One accelerator stack spans multiple generations, such as H100/H200/B200/B300/GB200/GB300, MI300X/MI325X/MI355X, TPU v5p/Trillium/Ironwood, or the Trainium family. This can apply to training, inference, or serving roles such as prefill and decode. The software path mostly carries over, but memory, fabric, availability, and tuning still differ. |
| **Different stacks, separate workloads** | Training, fine-tuning, evaluation, batch inference, and online inference run on different accelerator stacks depending on supply, cost, and readiness. This is the most practical cross-stack pattern because each workload keeps its own runtime, image, kernels, and failure modes. |
| **One endpoint, separate backends** | One user-facing endpoint routes whole requests to complete backends, each running on its own accelerator stack. This uses mixed capacity without splitting a single inference; each backend still has to meet the same behavior, context, latency, and fallback requirements. |
| **One training run across sites** | One training run spans clusters, regions, or datacenters, usually within the same accelerator and collective stack. This is capacity and fabric engineering, not generic portability; cross-vendor training remains frontier for most teams. |
| **One inference request across stacks** | Prefill/decode split across unlike accelerator stacks is emerging. The phases stress compute, memory bandwidth, and networking differently, but public evidence is mostly research or partner-specific. Assume experimental until the exact serving path is demonstrated. |

## Drivers

Most accelerator decisions come down to two practical questions: whether the team can get the right capacity, and whether the software stack is ready for the workload.

### Supply

Accelerator choice is now part of capacity planning, not just performance tuning. The question is often how soon a team can get the right cluster shape, in the right region, with the right interconnect, quota, reservation terms, and price. Teams look at alternatives when the most familiar path means waiting too long, committing too much, or accepting capacity that does not fit the workload. The public signals below show supply strategy, not neutral performance proof.

| Organization | Public figures | What it supports |
| :---- | :---- | :---- |
| Anthropic | Up to 1M [Google Cloud TPUs](https://www.anthropic.com/news/expanding-our-use-of-google-cloud-tpus-and-services); up to 5 GW of additional [AWS capacity using Trainium](https://www.anthropic.com/news/anthropic-amazon-compute) | Frontier labs are willing to run across cloud-owned accelerator stacks when capacity and economics justify it. |
| OpenAI | At least 10 GW of [NVIDIA systems](https://investor.nvidia.com/news/press-release-details/2025/OpenAI-and-NVIDIA-Announce-Strategic-Partnership-to-Deploy-10-Gigawatts-of-NVIDIA-Systems/default.aspx); 6 GW of [AMD GPUs](https://openai.com/index/openai-amd-strategic-partnership/) | Even the largest NVIDIA buyers are also pursuing merchant alternatives. |
| Meta | Up to 6 GW of [AMD Instinct GPUs](https://ir.amd.com/news-events/press-releases/detail/1279/amd-and-meta-announce-expanded-strategic-partnership-to-deploy-6-gigawatts-of-amd-gpus) | Large buyers are adding non-NVIDIA merchant GPUs to their supply plans. |

### Software

An accelerator path is only relevant when the software stack is ready for the workload. The key checks are:

- Baseline. NVIDIA remains the reference path for kernels, collectives, containers, debugging, profiling, and operator experience.
- Runtime path. AMD means ROCm/RCCL validation; TPUs mean XLA/JAX/PyTorch/XLA and Cloud TPU operations; Trainium means Neuron, compiler behavior, framework support, and AWS deployment paths.
- Serving path. TensorRT-LLM, Triton Inference Server, Dynamo, vLLM, and SGLang matter because serving support is model-, backend-, and feature-specific. Gateways route across qualified backends; they do not make stacks interchangeable.
- Model path. Attention kernels, quantization, precision, compiler behavior, and model-specific support can decide whether the workload is usable on a given accelerator.
- Specialized systems. Groq and Cerebras are evaluated through supported models, latency, output speed, context support, deployment path, and price rather than as general-purpose accelerator pools.

## Benchmarks

This is not a ranking of accelerators. Benchmark evidence is useful when it says something concrete about the system, workload, precision, scale, and software path being evaluated.

| Benchmark | What it shows | What it does not prove |
| :---- | :---- | :---- |
| **[MLPerf Training v6.0](https://mlcommons.org/2026/06/mlperf-training-v6-0-results/)** | Standardized training submissions are broadening: 95 submitted systems, 13 accelerator types, 24 submitting organizations, and 60% multi-node systems. | That a vendor is ready for every training stack, model architecture, provider image, or cluster shape. |
| **[MLPerf Inference v6.0](https://mlcommons.org/2026/04/mlperf-inference-v6-0-results/)** | Inference benchmarks are moving toward modern workloads, including new or updated datacenter tests and more multi-node submissions. | That service latency, cost, routing, KV cache behavior, or production failure modes will match the benchmark. |
| **Vendor MLPerf writeups: [NVIDIA](https://blogs.nvidia.com/blog/blackwell-mlperf-training-6-0/), [AMD](https://www.amd.com/en/blogs/2026/amd-delivers-breakthrough-mlperf-inference-6-0-results.html)** | Configuration details and vendor interpretation, such as NVIDIA's Training v6.0 sweep or AMD's MI355X above 1M tokens/sec in Inference v6.0. | A neutral cross-vendor summary; the vendor chooses what to emphasize. |
| **[SemiAnalysis InferenceX](https://inferencex.semianalysis.com/)** | Market and software movement as serving engines, kernels, quantization, and runtime choices improve, especially across NVIDIA and AMD GPU stacks. | A standardized benchmark suite or a complete market map across TPUs, Trainium, Groq, Cerebras, Tenstorrent, or every deployment path. |

## Readiness

Readiness turns theoretical supply into usable capacity. The question is not whether an accelerator exists or has a strong benchmark result. The question is whether a team can use it for training or inference without making the accelerator choice the project.

| Factor | What to check |
| :---- | :---- |
| **Capacity** | Generation, memory, node count, interconnect, region, quota, volume, wait time, commitment size, terms, and price. |
| **Software** | Model code and framework support, compiler/runtime behavior, precision support, kernels, collective libraries for distributed training, serving engines or gateways for inference, container images, and known model gaps. |
| **Performance** | Public results close to the intended model, precision, system shape, and scale, followed by direct testing on the provider image and stack the team will use. |
| **Orchestration** | Scheduling, quotas, monitoring, debugging, utilization, upgrades, failure recovery, support, and how portable the workload remains across providers or accelerator stacks. |

The opening vendor map separates readiness breadth, deployment flexibility, and adoption profile.

## Vendors

### Adoption profiles

Adoption profile describes where an accelerator is practical today.

| Adoption profile | Meaning |
| :---- | :---- |
| **Broad adoption** | Broad software support, public availability, familiar operations, and minimal rewrites. |
| **Early adopters** | More validation work is acceptable if the upside is large enough. |
| **Cloud-committed** | One hyperscaler runtime is acceptable, with lower portability. |
| **Specialized** | Supported models, latency, output speed, context, and price dominate. |

!!! info "Frontier buyers"

    For frontier buyers such as Anthropic, OpenAI, and Meta, supply is part of accelerator strategy. At their scale, capacity commitments can justify using NVIDIA or AMD fleets alongside cloud-owned accelerators such as TPUs and Trainium, even when that requires additional validation and integration work.

Deployment flexibility means whether the accelerator can be owned, rented, used through a specialized path, or used through one cloud stack.

### Vendor categories

| Category | Vendors | Why it is placed there |
| :---- | :---- | :---- |
| Open market | NVIDIA, AMD, Tenstorrent | Higher deployment flexibility: these accelerator paths are available outside one cloud owner. NVIDIA and AMD have broader public software and workload evidence; Tenstorrent remains earlier and more vendor-led. |
| Specialized inference | Groq, Cerebras | Medium deployment flexibility: not cloud-owned, but narrower and optimized for supported inference models. Readiness depends on latency, output speed, context, price, and vendor stack fit rather than broad CUDA/ROCm/XLA/Neuron or vLLM/SGLang coverage. |
| Cloud-owned | Google TPUs, AWS Trainium | Lower deployment flexibility: these accelerator paths are rented through the cloud that owns the chip and runtime. The trade-off is portability, not whether the stack is useful; both can be strong when the cloud commitment is acceptable. |

### Vendor readiness

| Vendor | Fits | Readiness signal | Main constraint |
| :---- | :---- | :---- | :---- |
| **NVIDIA** | Direct accelerator use across training, fine-tuning, batch inference, and self-hosted online inference in public clouds and private clusters. | The depth of the [CUDA](https://docs.nvidia.com/cuda/) ecosystem: kernels, [NCCL](https://docs.nvidia.com/deeplearning/nccl/), [TensorRT-LLM](https://docs.nvidia.com/tensorrt-llm/), [Triton Inference Server](https://docs.nvidia.com/deeplearning/triton-inference-server/index.html), [NVIDIA Dynamo](https://www.nvidia.com/en-us/ai/dynamo/), PyTorch support, provider images, debugging tools, and operator experience. NVIDIA's [MLPerf Training v6.0 writeup](https://blogs.nvidia.com/blog/blackwell-mlperf-training-6-0/) reports a clean sweep and being the only platform to submit on every test. | Supply, price, commitment terms, fabric availability, and dependency on an ecosystem that can become the default architecture if teams do not keep workloads portable. |
| **AMD** | Merchant GPU path outside an NVIDIA-only plan, with validation on the exact workload instead of assuming CUDA compatibility. | Whether the model runs well on [ROCm](https://rocm.docs.amd.com/en/latest/index.html) with the required precision, kernels, serving engine, provider image, [RCCL](https://rocm.docs.amd.com/projects/rccl/en/latest/index.html), and multi-GPU or multi-node shape. AMD's [MLPerf Training v6.0](https://www.amd.com/en/blogs/2026/amd-delivers-breakthrough-mlperf-training-6-0-results.html) and [Inference v6.0](https://www.amd.com/en/blogs/2026/amd-delivers-breakthrough-mlperf-inference-6-0-results.html) writeups show scale-out training progress and MI355X inference above one million tokens per second. | Software variance: ROCm version, framework path, model architecture, provider packaging, observability, and failure recovery can change the result. |
| **Tenstorrent** | Early adopters evaluating a direct accelerator path that is not tied to CUDA or a hyperscaler-owned runtime. | The [Galaxy Blackhole launch](https://tenstorrent.com/en/newsroom/tenstorrent-enables-ai-at-scale-with-industry-leading-performance), where Tenstorrent reports deployed superclusters, LLM and video-generation workload claims, and a stack built around TT-Metal, TT-NN, TT-Lang, and TT-Forge. | Public evidence is mostly vendor- or partner-led and workload-specific. Teams should validate model bring-up, framework coverage, kernel and compiler maturity, provider access, observability, and support before treating it as production capacity. |
| **TPU** | Google Cloud-anchored workloads that can build around XLA, JAX, PyTorch/XLA, and Cloud TPU infrastructure. | Anthropic's [Google Cloud TPU expansion](https://www.anthropic.com/news/expanding-our-use-of-google-cloud-tpus-and-services) is a public scale signal. Google Cloud's [Trillium MLPerf Training 4.1 writeup](https://cloud.google.com/blog/products/compute/trillium-mlperf-41-training-benchmarks/) and [Ironwood TPU7x](https://cloud.google.com/blog/products/compute/inside-the-ironwood-tpu-codesigned-ai-stack) show the stack moving to newer system-scale generations. | Portability: checkpoint movement, compiler behavior, quota, region availability, model support, and operational differences from GPU clusters. |
| **Trainium** | AWS-committed workloads that can build around [Neuron](https://awsdocs-neuron.readthedocs-hosted.com/) rather than treating it as a drop-in GPU replacement. | Anthropic's [AWS compute expansion](https://www.anthropic.com/news/anthropic-amazon-compute) is a public scale signal. [Trainium3 UltraServers](https://aws.amazon.com/ai/machine-learning/trainium/) show AWS packaging the Neuron path as larger system-scale infrastructure. Readiness depends on Neuron compiler/runtime behavior, framework integration, distributed training support, deployment tooling, and known model support. | Cloud-specific compiler and runtime stack. Teams should test compilation behavior, throughput, observability, and migration cost before relying on it. |
| **Groq and Cerebras** | Specialized cases for supported inference models, where latency, output speed, context, and price matter more than general accelerator access. | Service-level evidence: supported models, throughput, time to first token, context length, reliability, and price. Examples include Groq's [independent LLM benchmark note](https://groq.com/newsroom/groq-lpu-inference-engine-leads-in-first-independent-llm-benchmark) and Cerebras's [Llama 3.1 405B inference result](https://www.cerebras.ai/blog/llama-405b-inference). | Scope and independence. These systems are not general training infrastructure; Groq also sits closer to NVIDIA after its inference technology licensing and team deal, while Cerebras remains the cleaner independent specialized example. |

## Orchestration

Heterogeneous compute is only useful if teams can turn scattered capacity into runnable workloads. That requires more than a scheduler queue. Teams need a way to describe training jobs, fine-tuning, batch jobs, services, images, secrets, resources, and placement constraints without rewriting the workflow for every accelerator pool.

The role of orchestration is to absorb operational complexity: provisioning, placement, images, resources, queues, scaling, service topology, logs, retries, and capacity constraints. It still has to respect runtime constraints. CUDA, ROCm, XLA, Neuron, collective libraries, serving engines, kernels, and model support are not interchangeable, so the control plane matches workloads to compatible capacity rather than treating every accelerator as equivalent.

| Stack | Role and trade-off |
| :---- | :---- |
| Kubernetes | Strong substrate for containers, services, operators, and internal platforms. For AI, it often requires stitching together device plugins, vendor GPU operators, Dynamic Resource Allocation, Kueue or Volcano, Kubeflow, KubeRay, autoscaling, and serving layers. Kubernetes-native multi-cluster tooling helps when capacity is already Kubernetes, but it still leaves accelerator discovery, quotas, procurement, runtime images, and cross-cloud placement as platform work. |
| Slurm | Strong for large batch clusters, queueing, accounting, policy, and topology-aware placement. The limits are cloud-native and container-native workflows: real deployments often depend on local modules, queues, prolog/epilog scripts, plugins, and launch conventions. NVIDIA's SchedMD acquisition also makes Slurm vendor independence something teams should watch. |
| Emerging | AI-native control planes such as `dstack` and SkyPilot focus on making scattered accelerator capacity usable through higher-level workload definitions for training jobs, batch jobs, and services. They reduce the glue work created by fragmented clouds, clusters, accelerators, runtimes, and sites, which otherwise falls to platform teams. They still depend on each accelerator stack and serving runtime for kernels, images, collectives, routing, and performance. |

Distributed inference makes this boundary especially important. Runtimes such as SGLang, Dynamo, vLLM, Mooncake, and NIXL own routing, batching, prefill/decode behavior, and KV cache movement; orchestration makes those topologies deployable and operable across compatible capacity.

!!! info "Vendor independence"
    The orchestration and control-plane layer should not quietly become another accelerator dependency. NVIDIA acquired [Run:ai](https://blogs.nvidia.com/blog/runai/), a Kubernetes-based workload management platform, and [SchedMD](https://blogs.nvidia.com/blog/nvidia-acquires-schedmd/), the leading developer of Slurm. NVIDIA says Slurm will remain open-source and vendor-neutral, and its Run:ai messaging emphasizes choice and flexibility. Teams may still trust those projects, but heterogeneous compute makes vendor independence a practical requirement for the scheduler and control plane.

## Networking

For training, the practical case is usually one accelerator stack spread across sites, regions, or generations. The job still depends on a compatible collective stack: [NCCL](https://docs.nvidia.com/deeplearning/nccl/) for NVIDIA, [RCCL](https://rocm.docs.amd.com/projects/rccl/en/latest/index.html) for AMD, and cloud-specific fabrics for TPUs and Trainium. Full-system results such as [MLPerf Training](https://mlcommons.org/2026/06/mlperf-training-v6-0-results/) help qualify a same-stack cluster shape; they do not make cross-vendor training portable.

For inference, the practical case is disaggregated serving within a compatible stack: prefill workers, decode workers, routing, and a KV-transfer path. NVIDIA's [Dynamo disaggregated serving](https://docs.nvidia.com/dynamo/design-docs/disaggregated-serving) treats KV transfer as the critical path and calls out RDMA or an equivalent fast fabric for production cross-node deployments. [Mooncake](https://github.com/kvcache-ai/Mooncake), used by Kimi, makes the same point from the serving side: cache placement, topology-aware transfer, and request routing are now part of inference performance.

The market direction is toward more portable fabric and runtime boundaries, not arbitrary cross-stack execution. Ethernet efforts such as [Spectrum-X](https://www.nvidia.com/en-us/networking/spectrumx/), the [Ultra Ethernet Consortium](https://ultraethernet.org/ultra-ethernet-consortium-uec-launches-specification-1-0-transforming-ethernet-for-ai-and-hpc-at-scale/), [OCP ESUN](https://www.opencompute.org/blog/the-ocp-esun-10-specification-has-been-released), and AMD's [Helios](https://www.amd.com/en/blogs/2025/amd-helios-ai-rack-built-on-metas-2025-ocp-design.html) point to pressure for open, high-performance Ethernet in AI clusters. That can reduce fabric lock-in and make heterogeneous pools easier to operate, but it does not yet make CUDA, ROCm, XLA, Neuron, serving engines, kernels, or KV-cache paths interchangeable.

## Final takeaways

- **Compute shift.** Teams may not want more infrastructure complexity, but the market is moving there anyway. Capacity commitments, cloud-owned accelerators, merchant alternatives, and specialized inference systems are making more than one accelerator path relevant.
- **Supply.** Agents, inference, and larger model deployments increase demand for usable capacity. The practical question is not only which accelerator is faster, but which one is available in the right volume, region, cloud or data center, timeline, and commercial terms.
- **Software.** An accelerator path matters only if the model, framework, runtime, kernels, distributed training path, serving stack, containers, and debugging tools are ready enough for the workload.
- **Orchestration.** Kubernetes and Slurm remain important, but heterogeneous compute needs a higher-level way to provision, place, and operate workloads across fragmented clouds, clusters, datacenters, and accelerator stacks without leaving platform teams to stitch every path together themselves.
- **Networking.** For training, fabric and collectives qualify same-stack scale. For inference, KV-cache transfer, routing, and cache locality determine whether disaggregated serving works in production.

## Out of scope

- Custom silicon controlled by individual hyperscalers or frontier labs. It matters as a supply signal because large buyers can reserve or build capacity outside the public accelerator market, but it is not a generally adoptable path for most teams.
- Chinese accelerators, including Huawei Ascend and Cambricon. These may be important, especially in China, but comparable public data is limited and hard to verify from outside the region.
- CPU-only workloads. CPUs matter for agents, data processing, and application infrastructure, but this report focuses on accelerator paths for large-scale training and inference.
- Sandboxes and agent runtime infrastructure. Browser sandboxes, code-execution environments, and isolation layers matter for agent systems, but they are not accelerator paths.
- FPGAs and experimental silicon. This report focuses on mainstream AI accelerators used for large-scale training and inference.

> [dstack](https://github.com/dstackai/dstack/) is an open-source control plane for AI workloads. Teams use it to run training jobs, batch jobs, and model services across GPU clouds, Kubernetes, and on-prem clusters, while choosing capacity based on accelerator type, availability, quota, and price.
