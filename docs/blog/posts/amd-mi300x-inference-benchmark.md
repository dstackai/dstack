---
title: "Benchmarking Llama 3.1 405B on 8x AMD MI300X GPUs"
date: 2024-10-09
description: "Exploring how the inference performance of Llama 3.1 405B varies on 8x AMD MI300X GPUs across vLLM and TGI backends in different use cases."  
slug: amd-mi300x-inference-benchmark
---

# Benchmarking Llama 3.1 405B on 8x AMD MI300X GPUs

At `dstack`, we've been adding support for AMD GPUs with [SSH fleets](../../docs/concepts/fleets.md#ssh-fleets), 
so we saw this as a great chance to test our integration by benchmarking AMD GPUs. Our friends at 
[Hot Aisle :material-arrow-top-right-thin:{ .external }](https://hotaisle.xyz/){:target="_blank"}, who build top-tier 
bare metal compute for AMD GPUs, kindly provided the hardware for the benchmark.

<img src="https://github.com/dstackai/static-assets/blob/main/static-assets/images/dstack-hotaisle-amd-mi300x-prompt-v4.png?raw=true" width="750" />

<!-- more -->

With access to a bare metal machine with 8x AMD MI300X GPUs from Hot Aisle, we decided to skip smaller models and went
with Llama 3.1 405B. To make the benchmark interesting, we tested how inference performance varied across different
backends (vLLM and TGI) and use cases (real-time vs batch inference, different context sizes, etc.).

## Benchmark setup

Here is the spec of the bare metal machine we got:

- Intel® Xeon® Platinum 8470 2G, 52C/104T, 16GT/s, 105M Cache, Turbo, HT (350W) [x2]
- AMD MI300X GPU OAM 192GB 750W GPUs [x8]
- 64GB RDIMM, 4800MT/s Dual Rank [x32]

??? info "Set up an SSH fleet"

    Hot Aisle provided us with SSH access to the machine. To make it accessible via `dstack`,
    we created an [SSH fleet](../../docs/concepts/fleets.md#ssh-fleets) using the following configuration:

    <div editor-title="hotaisle.dstack.yml"> 

    ```yaml
    type: fleet
    name: hotaisle-fleet
    
    placement: any
    
    ssh_config:
      user: hotaisle
      identity_file: ~/.ssh/hotaisle_id_rsa
    
      hosts:
        - hostname: ssh.hotaisle.cloud
          port: 22013
    ```

    </div>

    After running `dstack apply -f hotaisle.dstack.yml`, we were ready to run dev environments, tasks, and services on
    this fleet via `datack`.

??? info "vLLM"
    
    ```
    PyTorch version: 2.4.1+rocm6.1
    Is debug build: False
    CUDA used to build PyTorch: N/A
    ROCM used to build PyTorch: 6.1.40091-a8dbc0c19
    
    OS: Ubuntu 22.04.4 LTS (x86_64)
    GCC version: (Ubuntu 11.4.0-1ubuntu1~22.04) 11.4.0
    Clang version: 17.0.0 (https://github.com/RadeonOpenCompute/llvm-project roc-6.1.0 24103 7db7f5e49612030319346f900c08f474b1f9023a)
    CMake version: version 3.26.4
    Libc version: glibc-2.35
    
    Python version: 3.10.14 (main, Mar 21 2024, 16:24:04) [GCC 11.2.0] (64-bit runtime)
    Python platform: Linux-6.8.0-45-generic-x86_64-with-glibc2.35
    Is CUDA available: True
    CUDA runtime version: Could not collect
    CUDA_MODULE_LOADING set to: LAZY
    GPU models and configuration: AMD Instinct MI300X (gfx942:sramecc+:xnack-)
    Nvidia driver version: Could not collect
    cuDNN version: Could not collect
    HIP runtime version: 6.1.40093
    MIOpen runtime version: 3.1.0
    Is XNNPACK available: True
    
    Versions of relevant libraries:
    [pip3] mypy==1.4.1
    [pip3] mypy-extensions==1.0.0
    [pip3] numpy==1.26.4
    [pip3] pytorch-triton-rocm==3.0.0
    [pip3] pyzmq==24.0.1
    [pip3] torch==2.4.1+rocm6.1
    [pip3] torchaudio==2.4.1+rocm6.1
    [pip3] torchvision==0.16.1+fdea156
    [pip3] transformers==4.45.1
    [pip3] triton==3.0.0
    [conda] No relevant packages
    ROCM Version: 6.1.40091-a8dbc0c19
    Neuron SDK Version: N/A
    vLLM Version: 0.6.3.dev116+g151ef4ef
    vLLM Build Flags:
    CUDA Archs: Not Set; ROCm: Disabled; Neuron: Disabled
    ```

??? info "TGI"

    The `ghcr.io/huggingface/text-generation-inference:sha-11d7af7-rocm` Docker image was used.

For conducting the tests, we've been using the [
`benchmark_serving` :material-arrow-top-right-thin:{ .external }](https://github.com/vllm-project/vllm/blob/main/benchmarks/benchmark_serving.py){:target="_blank"} provided by vLLM. 

## Observations

### Token/sec per batch size
TGI outperforms vLLM across all batch sizes in terms of token throughput. The performance gap increases as the batch size increases. For batches larger than 64, there is significant difference in performance. The sequence lengths of prompts are kept constant at 80 tokens per prompt.
![chart1](https://raw.githubusercontent.com/dstackai/benchmarks/refs/heads/main/amd/inference/charts_short_seq/throughput_tgi_vllm.png)

### TTFT per batch size
TGI outperforms vLLM in Time To First Token across all batch sizes except batch size 2 & 32. Here too the performance gap is significant at larger batches.
![chart2](https://raw.githubusercontent.com/dstackai/benchmarks/refs/heads/main/amd/inference/charts_short_seq/ttft_mean_tgi_vllm.png)

### Token/sec per context size
To check the performance in larger prompt sizes we conducted the tests at 10000 tokens per prompt. Here too, in terms of token throughput and TTFT,
TGI outperformed vLLM significantly.
![chart3](https://raw.githubusercontent.com/dstackai/benchmarks/refs/heads/main/amd/inference/charts_long_seq/throughput_tgi_vllm.png)
![chart4](https://raw.githubusercontent.com/dstackai/benchmarks/refs/heads/main/amd/inference/charts_long_seq/mean_ttft_tgi_vllm.png)

### Token/sec per RPS & TTFT per RPS
To evaluate the performance scalability of TGI & vLLM we conducted tests with increasing Request Per Second (RPS) and increasing Requests Sent (RS) with same prompt size of 1000 tokens in all runs. In this experiment, we sent requests starting from 
30 Requests at 1 RPS, 60 Requests at 2 RPS, ...,  to 150 Requests at 5 RPS. Ideally, all the runs should complete within same time frame, however due to limitation in resources as well as resource utilization increasing RPS will
not proportionally increase the throughout (token/s) and maintain TTFT. Below observations show how both backends behave. 

At low 1 RPS(Request Per Second), vLLM is slightly better than TGI. Between 2 and 4 RPS,  TGI outperforms significantly in both token/s and TTFT.
However, TGI starts to drop requests after 5 RPS
![chart5](https://raw.githubusercontent.com/dstackai/benchmarks/refs/heads/main/amd/inference/charts_rps/token_per_second_low_tgi_vllm.png)
![chart6](https://raw.githubusercontent.com/dstackai/benchmarks/refs/heads/main/amd/inference/charts_rps/mean_ttft_low_tgi_vllm.png)

We conducted same test with larger number of requests (300 to 900). At 900 requests with 3 RPS, TGI dropped most of the requests, however performed significantly better below 900 Requests.
![chart7](https://raw.githubusercontent.com/dstackai/benchmarks/refs/heads/main/amd/inference/charts_rps/token_per_second_tpi_vllm.png)
![chart8](https://raw.githubusercontent.com/dstackai/benchmarks/refs/heads/main/amd/inference/charts_rps/mean_ttft_tgi_vllm.png)

### vRAM consumption

#### TGI

```
============================================ ROCm System Management Interface ============================================
====================================================== Concise Info ======================================================
Device  Node  IDs              Temp        Power     Partitions          SCLK    MCLK    Fan  Perf  PwrCap  VRAM%  GPU%  
              (DID,     GUID)  (Junction)  (Socket)  (Mem, Compute, ID)                                                  
==========================================================================================================================
0       2     0x74a1,   55354  47.0°C      139.0W    NPS1, SPX, 0        132Mhz  900Mhz  0%   auto  750.0W  68%    0%    
1       3     0x74a1,   41632  40.0°C      135.0W    NPS1, SPX, 0        131Mhz  900Mhz  0%   auto  750.0W  68%    0%    
2       4     0x74a1,   47045  44.0°C      136.0W    NPS1, SPX, 0        132Mhz  900Mhz  0%   auto  750.0W  68%    0%    
3       5     0x74a1,   60169  48.0°C      143.0W    NPS1, SPX, 0        132Mhz  900Mhz  0%   auto  750.0W  68%    0%    
4       6     0x74a1,   56024  46.0°C      139.0W    NPS1, SPX, 0        132Mhz  900Mhz  0%   auto  750.0W  68%    0%    
5       7     0x74a1,   705    42.0°C      136.0W    NPS1, SPX, 0        131Mhz  900Mhz  0%   auto  750.0W  68%    0%    
6       8     0x74a1,   59108  51.0°C      144.0W    NPS1, SPX, 0        132Mhz  900Mhz  0%   auto  750.0W  68%    0%    
7       9     0x74a1,   10985  44.0°C      138.0W    NPS1, SPX, 0        132Mhz  900Mhz  0%   auto  750.0W  68%    0%    
==========================================================================================================================
================================================== End of ROCm SMI Log ===================================================
```

#### vLLM

```shell
========================================= ROCm System Management Interface =========================================
=================================================== Concise Info ===================================================
Device  [Model : Revision]    Temp        Power     Partitions      SCLK    MCLK    Fan  Perf  PwrCap  VRAM%  GPU%  
        Name (20 chars)       (Junction)  (Socket)  (Mem, Compute)                                                  
====================================================================================================================
0       [0x74a1 : 0x00]       47.0°C      139.0W    NPS1, SPX       132Mhz  900Mhz  0%   auto  750.0W   97%   0%    
        AMD Instinct MI300X                                                                                         
1       [0x74a1 : 0x00]       39.0°C      135.0W    NPS1, SPX       131Mhz  900Mhz  0%   auto  750.0W   95%   0%    
        AMD Instinct MI300X                                                                                         
2       [0x74a1 : 0x00]       44.0°C      136.0W    NPS1, SPX       132Mhz  900Mhz  0%   auto  750.0W   95%   0%    
        AMD Instinct MI300X                                                                                         
3       [0x74a1 : 0x00]       48.0°C      143.0W    NPS1, SPX       132Mhz  900Mhz  0%   auto  750.0W   95%   0%    
        AMD Instinct MI300X                                                                                         
4       [0x74a1 : 0x00]       46.0°C      138.0W    NPS1, SPX       132Mhz  900Mhz  0%   auto  750.0W   95%   0%    
        AMD Instinct MI300X                                                                                         
5       [0x74a1 : 0x00]       41.0°C      137.0W    NPS1, SPX       131Mhz  900Mhz  0%   auto  750.0W   95%   0%    
        AMD Instinct MI300X                                                                                         
6       [0x74a1 : 0x00]       51.0°C      143.0W    NPS1, SPX       132Mhz  900Mhz  0%   auto  750.0W   95%   0%    
        AMD Instinct MI300X                                                                                         
7       [0x74a1 : 0x00]       43.0°C      137.0W    NPS1, SPX       132Mhz  900Mhz  0%   auto  750.0W   95%   0%    
        AMD Instinct MI300X                                                                                         
====================================================================================================================
=============================================== End of ROCm SMI Log ================================================
```

## Notes
* Inference backend configurations play a crucial role in determining the efficiency and scalability of both TGI and vLLM backends. The current benchmarks were conducted on a specific server setup, but to gain a comprehensive understanding of the performance capabilities more combinations of server configurations should be explored.
* While it was observed that TGI consumes less VRAM compared to vLLM on AMD hardware, more investigation is needed to fully understand the VRAM utilization patterns of both backends. 

## Conclusion
TGI is better for moderate to high workloads, handling increasing RPS more effectively up to certain limits. It delivers faster TTFT and higher throughput in these scenarios.
vLLM performs well at low RPS, but its scalability is limited, making it less effective for higher workloads. TGI's performance advantage lies in its [continuous batching algorithm](https://huggingface.co/blog/martinigoyanes/llm-inference-at-scale-with-tgi), which dynamically adjusts the size of batches, maximizes GPU utilization. 
When considering VRAM consumption, it's clear that TGI is better optimized for AMD GPUs. This more efficient use of VRAM allows TGI to handle larger workloads and maintain higher throughput and lower latency  
## What's next?

While we wait for AMD to announce new GPUs and for data centers to offer them, we’re considering tests with NVIDIA GPUs
like the H100 and H200, and possibly Google TPU.

If you’d like to support us in doing more benchmarks, please let us know.

### Source code

The source code used for this benchmark can be found in our 
[GitHub repo :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/benchmarks/tree/main/amd/inference){:target="_blank"}.

If you have questions, feedback, or want to help improve the benchmark, please reach out to our team.

## Thanks to our friends

### Hot Aisle

[Hot Aisle :material-arrow-top-right-thin:{ .external }](https://hotaisle.xyz/){:target="_blank"} 
is the primary sponsor of this benchmark, and we are sincerely grateful for their hardware and support.  
If you'd like to use top-tier bare metal compute with AMD GPUs, we recommend going
with Hot Aisle. Once you gain access to a cluster, it can be easily accessed via `dstack`'s [SSH fleet](../../docs/concepts/fleets.md#ssh-fleets) easily.

### RunPod
If you’d like to use on-demand compute with AMD GPUs at affordable prices, you can configure `dstack` to
use [RunPod :material-arrow-top-right-thin:{ .external }](https://runpod.io/){:target="_blank"}. In
this case, `dstack` will be able to provision fleets automatically when you run dev environments, tasks, and
services.
