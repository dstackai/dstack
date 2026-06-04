---
title: "The state of heterogeneous AI compute in 2026"
date: 2026-06-05
description: "How supply, software readiness, orchestration, and networking shape accelerator choices across NVIDIA, AMD, TPUs, Trainium, and specialized inference systems."
slug: state-of-heterogeneous-compute-2026
categories:
  - Reports
---

# The state of heterogeneous AI compute in 2026

Heterogeneous AI compute is becoming harder to ignore. The reason is practical: supply pressure, pricing, and stack readiness are making more than one accelerator path worth evaluating.

This report focuses on accelerator choices behind training and inference workloads: the main patterns, the evidence behind them, how readiness differs across NVIDIA, AMD, TPUs, Trainium, and specialized inference systems, and why orchestration and networking determine whether capacity can be used in practice.

<!-- more -->

## Patterns

Heterogeneous AI compute covers several practical patterns. Mixing accelerator generations, placing separate workloads on different pools, and coordinating work across sites all have different readiness requirements.

| Pattern | What it looks like |
| :---- | :---- |
| **Different generations, same stack** | One accelerator stack spans multiple generations, such as H100/H200/B200/GB200, TPU v5p/Trillium, or Trainium/Trainium2. The software path is familiar, but capacity, memory, placement, and performance tuning still differ. |
| **Separate pools, different accelerators** | Training, fine-tuning, evaluation, batch inference, and online inference run on different accelerator pools depending on supply, cost, and software readiness. |
| **Distributed training across pools** | One training run coordinates multiple clusters, regions, or datacenters, usually within the same accelerator stack. Cross-vendor training remains a research-grade case for most teams. |
| **Distributed inference across heterogeneous pools** | Inference for the same product or model family is routed across regions, clusters, or accelerator pools. The hard parts are latency, model/version parity, traffic shaping, and observability. |

## Drivers

Most accelerator decisions come down to two practical questions: whether the team can get the right capacity, and whether the software stack is ready for the workload.

### Supply

Accelerator choice is now part of capacity planning, not just performance tuning. The question is often how soon a team can get the right cluster shape, in the right region, with the right interconnect, quota, reservation terms, and price. Teams look at alternatives when the most familiar path means waiting too long, committing too much, or accepting capacity that does not fit the workload.

| Organization | Public figures | What it supports |
| :---- | :---- | :---- |
| Anthropic | Up to 1M [Google Cloud TPUs](https://www.anthropic.com/news/expanding-our-use-of-google-cloud-tpus-and-services); up to 5 GW of additional [AWS capacity using Trainium](https://www.anthropic.com/news/anthropic-amazon-compute) | Frontier labs are willing to run across cloud-owned accelerator stacks when capacity and economics justify it. |
| OpenAI | At least 10 GW of [NVIDIA systems](https://investor.nvidia.com/news/press-release-details/2025/OpenAI-and-NVIDIA-Announce-Strategic-Partnership-to-Deploy-10-Gigawatts-of-NVIDIA-Systems/default.aspx); 6 GW of [AMD GPUs](https://openai.com/index/openai-amd-strategic-partnership/) | Even the largest NVIDIA buyers are also pursuing merchant alternatives. |
| Meta | Up to 6 GW of [AMD Instinct GPUs](https://ir.amd.com/news-events/press-releases/detail/1279/amd-and-meta-announce-expanded-strategic-partnership-to-deploy-6-gigawatts-of-amd-gpus) | Large buyers are adding non-NVIDIA merchant GPUs to their supply plans. |

These are supply signals, not neutral performance proof.

### Software

An accelerator path is only relevant when the software stack is ready for the workload. The key checks are:

- CUDA baseline. NVIDIA remains the reference point for kernels, NCCL collectives, PyTorch support, container images, profiling, debugging, and operator experience.
- Alternative stacks. AMD means ROCm, RCCL, PyTorch ROCm builds, containers, and serving support. TPUs mean XLA, JAX, PyTorch/XLA, Cloud TPU infrastructure, and TPU support in open serving stacks. Trainium means Neuron, framework integration, distributed training support, and AWS-managed deployment paths.
- Serving layer. NVIDIA-led tools such as TensorRT-LLM, Triton Inference Server, and Dynamo matter for the NVIDIA path. vLLM, SGLang, and Shepherd Model Gateway matter because they push more serving work toward cross-vendor engines and gateways.
- Kernels. FlashAttention-class work matters because support for the exact model, precision, and accelerator can change the result materially.
- Specialized inference. Groq and Cerebras are evaluated through supported models, latency, output speed, context support, deployment path, and price rather than as general-purpose accelerator pools.

## Benchmarks

This is not a ranking of accelerators. Benchmark evidence is useful when it says something concrete about the system being evaluated:

- Neutral coverage. [MLPerf Training](https://mlcommons.org/2025/11/training-v5-1-results/) and [MLPerf Inference](https://mlcommons.org/2026/04/mlperf-inference-v6-0-results/) show which vendors submit full systems, at what scale, and on which workloads.
- Vendor interpretation. Vendor MLPerf writeups are useful for configuration details and claims such as NVIDIA's Training v5.1 sweep or AMD's MI355X Inference v6.0 results, but they should not be read as neutral summaries.
- Software movement. [SemiAnalysis InferenceX](https://inferencex.semianalysis.com/) is useful because inference results can change as serving engines, kernels, quantization, and runtime choices improve.
- Scope. A benchmark still has to match the model, precision, latency target, system size, provider image, and failure mode the team actually cares about.

| Benchmark | What it shows | What it does not prove |
| :---- | :---- | :---- |
| **[MLPerf Training v5.1](https://mlcommons.org/2025/11/training-v5-1-results/)** | Training evidence is broadening: 65 submitted systems, 12 accelerator types, 20 organizations, and more multi-node submissions. | That a vendor is ready for every training stack, model architecture, provider image, or cluster shape. |
| **[MLPerf Inference v6.0](https://mlcommons.org/2026/04/mlperf-inference-v6-0-results/)** | Inference benchmarks are moving toward modern workloads, including new or updated datacenter tests and more multi-node submissions. | That service latency, cost, routing, KV cache behavior, or production failure modes will match the benchmark. |
| **Vendor MLPerf writeups: [NVIDIA](https://blogs.nvidia.com/blog/mlperf-training-benchmark-blackwell-ultra/), [AMD](https://www.amd.com/en/blogs/2026/amd-delivers-breakthrough-mlperf-inference-6-0-results.html)** | Vendor-specific claims and configuration details, such as NVIDIA's Training v5.1 sweep or AMD's MI355X above 1M tokens/sec in Inference v6.0. | A neutral cross-vendor summary; the vendor chooses what to emphasize. |
| **[SemiAnalysis InferenceX](https://inferencex.semianalysis.com/)** | How inference results move as serving engines, kernels, quantization, and runtime choices improve, especially across NVIDIA and AMD GPU stacks. | A complete market map across TPUs, Trainium, Groq, Cerebras, Tenstorrent, or every deployment path. |

## Readiness

Readiness turns theoretical supply into usable capacity. The question is not whether an accelerator exists or has a strong benchmark result. The question is whether a team can use it for training or inference without making the accelerator choice the project.

| Factor | What to check |
| :---- | :---- |
| **Capacity** | Generation, memory, node count, interconnect, region, quota, volume, wait time, commitment size, terms, and price. |
| **Software** | Model code and framework support, compiler/runtime behavior, precision support, kernels, collective libraries for distributed training, serving engines or gateways for inference, container images, and known model gaps. |
| **Performance** | Public results close to the intended model, precision, system shape, and scale, followed by direct testing on the provider image and stack the team will use. |
| **Orchestration** | Scheduling, quotas, monitoring, debugging, utilization, upgrades, failure recovery, support, and how portable the workload remains across providers or accelerator stacks. |

The vendor map below applies these checks by readiness breadth and adoption profile.

## Vendors

### Adoption profiles

Adoption profile means who can realistically use an accelerator path today.

| Adoption profile | Meaning |
| :---- | :---- |
| **General teams** | Need broad software support, public availability, familiar operations, and minimal rewrites. |
| **Early adopters** | Can take on more validation work if the upside is large enough. |
| **Cloud-committed teams** | Can build around one hyperscaler runtime and accept lower portability. |
| **Specialized inference users** | Care most about supported models, latency, output speed, context, and price. |

The chart maps readiness breadth on the x-axis and adoption profile on the y-axis.

```text
                                      breadth of readiness
adoption profile       narrower --------------------------------> broader

General teams                  |                         AMD                      NVIDIA

Early adopter teams            |        Tenstorrent

Cloud-committed teams          |     Trainium        TPU

Specialized inference users    |        Groq / Cerebras
```

Use the chart as a starting point; the real position changes with the model, provider, region, quota, fabric, and serving or training stack.

### Vendor categories

| Category | Vendors | What it means |
| :---- | :---- | :---- |
| Own or rent | NVIDIA, AMD, Tenstorrent | Direct accelerator paths that can be installed or rented, depending on availability. NVIDIA and AMD have broader evidence; Tenstorrent is earlier. |
| Vendor appliance | Groq, Cerebras | Specialized inference systems where the vendor stack is part of the deployment model, such as [GroqRack](https://groq.com/groqrack/) or [Cerebras CS-3](https://www.cerebras.ai/product-system). |
| Cloud-only | Google TPUs, AWS Trainium | Cloud-owned accelerator stacks with their own compiler/runtime path, used through [Google Cloud TPU](https://cloud.google.com/tpu/docs) or [AWS Trainium](https://aws.amazon.com/ai/machine-learning/trainium/). |

### Vendor readiness

| Vendor | Fits | Readiness signal | Main constraint |
| :---- | :---- | :---- | :---- |
| **NVIDIA** | Direct accelerator use across training, fine-tuning, batch inference, and self-hosted online inference in public clouds and private clusters. | The depth of the [CUDA](https://docs.nvidia.com/cuda/) ecosystem: kernels, [NCCL](https://docs.nvidia.com/deeplearning/nccl/), [TensorRT-LLM](https://docs.nvidia.com/tensorrt-llm/), [Triton Inference Server](https://docs.nvidia.com/deeplearning/triton-inference-server/index.html), [NVIDIA Dynamo](https://www.nvidia.com/en-us/ai/dynamo/), PyTorch support, provider images, debugging tools, and operator experience. NVIDIA's [MLPerf Training v5.1 writeup](https://blogs.nvidia.com/blog/mlperf-training-benchmark-blackwell-ultra/) reports submitting on every test and sweeping all seven tests. The [Groq licensing and team deal](https://groq.com/newsroom/groq-and-nvidia-enter-non-exclusive-inference-technology-licensing-agreement-to-accelerate-ai-inference-at-global-scale) also points to NVIDIA expanding its inference roadmap beyond GPUs. | Supply, price, commitment terms, fabric availability, and dependency on an ecosystem that can become the default architecture if teams do not keep workloads portable. |
| **AMD** | Teams that want a merchant GPU path outside an NVIDIA-only plan and can test the exact workload instead of assuming CUDA compatibility. | Whether the model runs well on [ROCm](https://rocm.docs.amd.com/en/latest/index.html) with the required precision, kernels, serving engine, provider image, [RCCL](https://rocm.docs.amd.com/projects/rccl/en/latest/index.html), and multi-GPU or multi-node shape. AMD's [MLPerf Inference v6.0 writeup](https://www.amd.com/en/blogs/2026/amd-delivers-breakthrough-mlperf-inference-6-0-results.html) reports MI355X surpassing one million tokens per second at multinode scale. | Software variance: ROCm version, framework path, model architecture, provider packaging, observability, and failure recovery can change the result. |
| **Tenstorrent** | Early adopter teams evaluating a direct accelerator path that is not tied to CUDA or a hyperscaler-owned runtime. | The [Galaxy Blackhole and TT-Deploy launch](https://tenstorrent.com/newsroom/tt-deploy), where Tenstorrent says the system is shipping in volume and describes a stack built around TT-Metal, TT-NN, TT-Lang, and TT-Forge. | Public evidence is mostly vendor-led and workload-specific. Teams should validate model bring-up, framework coverage, kernel and compiler maturity, provider access, observability, and support before treating it as production capacity. |
| **TPU** | Teams anchored in Google Cloud or willing to build around XLA, JAX, PyTorch/XLA, and Cloud TPU infrastructure. | Anthropic's [Google Cloud TPU expansion](https://www.anthropic.com/news/expanding-our-use-of-google-cloud-tpus-and-services) is a public scale signal. Google Cloud's [Trillium MLPerf Training 4.1 writeup](https://cloud.google.com/blog/products/compute/trillium-mlperf-41-training-benchmarks/) is a measurable benchmark signal. | Portability: checkpoint movement, compiler behavior, quota, region availability, model support, and operational differences from GPU clusters. |
| **Trainium** | AWS-committed teams that can build around [Neuron](https://awsdocs-neuron.readthedocs-hosted.com/) rather than treating it as a drop-in GPU replacement. | Anthropic's [AWS compute expansion](https://www.anthropic.com/news/anthropic-amazon-compute) is a public scale signal. Readiness depends on Neuron compiler/runtime behavior, framework integration, distributed training support, deployment tooling, and known model support. | Cloud-specific compiler and runtime stack. Teams should test compilation behavior, throughput, observability, and migration cost before relying on it. |
| **Groq and Cerebras** | Specialized inference cases for supported models, where latency, output speed, context, and price matter more than general accelerator access. | Service-level evidence: supported models, throughput, time to first token, context length, reliability, and price. Examples include Groq's [independent LLM benchmark note](https://groq.com/newsroom/groq-lpu-inference-engine-leads-in-first-independent-llm-benchmark) and Cerebras's [Llama 3.1 405B inference result](https://www.cerebras.ai/blog/llama-405b-inference). | Scope and independence. These systems are not general training infrastructure; Groq also sits closer to NVIDIA after its inference technology licensing and team deal, while Cerebras remains the cleaner independent specialized-inference example. |

## Orchestration

Heterogeneous compute is only useful if teams can turn scattered capacity into runnable workloads. That requires more than a scheduler queue. Teams need a way to describe training jobs, fine-tuning, batch jobs, services, images, secrets, resources, and placement constraints without rewriting the workflow for every accelerator pool.

Orchestration does not make ROCm behave like CUDA or make a TPU workload portable by itself. Its job is to expose usable capacity, match workloads to compatible pools, keep task and service definitions portable where possible, and give platform teams one control layer across clouds, Kubernetes clusters, Slurm clusters, and on-prem infrastructure.

| Stack | Role and trade-off |
| :---- | :---- |
| Kubernetes | Strong substrate for containers, services, operators, and internal platforms. For AI, the stack is fragmented across device plugins, Dynamic Resource Allocation, GPU operators, Kueue, Volcano, Kubeflow, KubeRay, autoscaling, and serving layers. Teams still need a higher-level interface for accelerator discovery, quotas, procurement, placement, and workload submission. |
| Slurm | Strong for large batch clusters, queueing, accounting, policy, and topology-aware placement. The limits are cloud-native and container-native workflows: real deployments often depend on local modules, queues, prolog/epilog scripts, plugins, and launch conventions. NVIDIA's SchedMD acquisition also makes Slurm vendor independence something teams should watch. |
| Emerging | AI-native control planes such as dstack and SkyPilot focus on provisioning, placement, portable task and service definitions, and running workloads across providers or clusters. They can integrate with Kubernetes, Slurm, clouds, or on-prem infrastructure, but still depend on each accelerator stack for kernels, images, quotas, and performance. |

!!! info "Vendor independence"
    The orchestration and control-plane layer should not quietly become another accelerator dependency. NVIDIA acquired [Run:ai](https://blogs.nvidia.com/blog/runai/), a Kubernetes-based workload management platform, and [SchedMD](https://blogs.nvidia.com/blog/nvidia-acquires-schedmd/), the leading developer of Slurm. NVIDIA says Slurm will remain open-source and vendor-neutral, and its Run:ai messaging emphasizes choice and flexibility. Teams may still trust those projects, but heterogeneous compute makes vendor independence a practical requirement for the scheduler and control plane.

## Networking

Networking is part of accelerator readiness, not a separate infrastructure detail.

For distributed training, capacity is usable only if the fabric and collective stack can scale the job reliably. This is where [NCCL](https://docs.nvidia.com/deeplearning/nccl/), [RCCL](https://rocm.docs.amd.com/projects/rccl/en/latest/index.html), cloud-specific TPU and Trainium fabrics, and full-system results such as [MLPerf Training](https://mlcommons.org/2025/11/training-v5-1-results/) matter.

For inference, networking matters because serving is moving beyond simple replicas. Prefill/decode split, KV cache movement, cache locality, and request routing make the network part of latency and throughput. NVIDIA's [Dynamo disaggregated serving](https://docs.nvidia.com/dynamo/design-docs/disaggregated-serving) and [NIXL](https://github.com/ai-dynamo/nixl), and vLLM's [Mooncake Store](https://vllm.ai/blog/2026-05-06-mooncake-store), point in that direction.

The open question is portability. Ethernet has momentum through [Spectrum-X](https://www.nvidia.com/en-us/networking/spectrumx/), the [Ultra Ethernet Consortium](https://ultraethernet.org/ultra-ethernet-consortium-uec-launches-specification-1-0-transforming-ethernet-for-ai-and-hpc-at-scale/), [OCP ESUN](https://www.opencompute.org/blog/the-ocp-esun-10-specification-has-been-released), and AMD's [Helios](https://www.amd.com/en/blogs/2025/amd-helios-ai-rack-built-on-metas-2025-ocp-design.html), but teams still need to validate the exact fabric, collective path, serving engine, and failure mode before assuming capacity is interchangeable.

## Final takeaways

- **Compute shift.** Teams may not want more infrastructure complexity, but the market is moving there anyway. Capacity commitments, cloud-owned accelerators, merchant alternatives, and specialized inference systems are making more than one accelerator path relevant.
- **Supply.** Agents, inference, and larger model deployments increase demand for usable capacity. The practical question is not only which accelerator is faster, but which one is available in the right volume, region, cloud or data center, timeline, and commercial terms.
- **Software.** An accelerator path matters only if the model, framework, runtime, kernels, distributed training path, serving stack, containers, and debugging tools are ready enough for the workload.
- **Orchestration.** Kubernetes and Slurm remain important, but heterogeneous compute needs a higher-level way to provision, place, and operate workloads across clouds, clusters, and accelerator stacks.

## Outside of the scope

- Custom silicon controlled by individual hyperscalers or frontier labs. It matters as a supply signal because large buyers can reserve or build capacity outside the public accelerator market, but it is not a generally adoptable path for most teams.
- Chinese accelerators, including Huawei Ascend and Cambricon. These may be important, especially in China, but comparable public data is limited and hard to verify from outside the region.
- CPU-only workloads. CPUs matter for agents, data processing, and application infrastructure, but this report focuses on accelerator paths for large-scale training and inference.
- Sandboxes and agent runtime infrastructure. Browser sandboxes, code-execution environments, and isolation layers matter for agent systems, but they are not accelerator paths.
- FPGAs and experimental silicon. This report focuses on mainstream AI accelerators used for large-scale training and inference.

> [dstack](https://github.com/dstackai/dstack/) is an open-source control plane for AI workloads. Teams use it to run training jobs, batch jobs, and model services across GPU clouds, Kubernetes, and on-prem clusters, while choosing capacity based on accelerator type, availability, quota, and price.
