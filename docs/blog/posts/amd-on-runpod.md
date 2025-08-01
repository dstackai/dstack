---
title: Supporting AMD accelerators on RunPod
date: 2024-08-21
description: "dstack, the open-source AI container orchestration platform, adds support for AMD accelerators, with RunPod as the first supported cloud provider."  
slug: amd-on-runpod
categories:
  - Changelog
---

# Supporting AMD accelerators on RunPod

While `dstack` helps streamline the orchestration of containers for AI, its primary goal is to offer vendor independence
and portability, ensuring compatibility across different hardware and cloud providers.

Inspired by the recent `MI300X` benchmarks, we are pleased to announce that RunPod is the first cloud provider to offer
AMD GPUs through `dstack`, with support for other cloud providers and on-prem servers to follow.

<!-- more -->

## Specification

For the reference, below is a comparison of the `MI300X` and `H100 SXM` specs, incl. the prices offered by RunPod.

|                                 | MI300X                                    | H100X SXM    |
|---------------------------------|-------------------------------------------|--------------|
| **On-demand pricing**           | $3.99/hr                                  | $3.99/hr     |
| **VRAM**                        | 192 GB                                    | 80GB         |
| **Memory bandwidth**            | 5.3 TB/s                                  | 3.4TB/s      |
| **FP16**                        | 2,610 TFLOPs                              | 1,979 TFLOPs |
| **FP8**                         | 5,220 TFLOPs                              | 3,958 TFLOPs |

One of the main advantages of the `MI300X` is its VRAM. For example, with the `H100 SXM`, you wouldn't be able to fit the FP16
version of Llama 3.1 405B into a single node with 8 GPUs—you'd have to use FP8 instead. However, with the `MI300X`, you
can fit FP16 into a single node with 8 GPUs, and for FP8, you'd only need 4 GPUs.

With the [latest update :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/releases/0.18.11rc1){:target="_blank"},
you can now specify an AMD GPU under `resources`. Below are a few examples.

## Configuration

=== "Service"
    Here's an example of a [service](../../docs/concepts/services.md) that deploys
    Llama 3.1 70B in FP16 using [TGI :material-arrow-top-right-thin:{ .external }](https://huggingface.co/docs/text-generation-inference/en/installation_amd){:target="_blank"}.
    
    <div editor-title="examples/inference/tgi/amd/service.dstack.yml"> 
    
    ```yaml
    type: service
    name: amd-service-tgi
    
    image: ghcr.io/huggingface/text-generation-inference:sha-a379d55-rocm
    env:
      - HF_TOKEN
      - MODEL_ID=meta-llama/Meta-Llama-3.1-70B-Instruct
      - TRUST_REMOTE_CODE=true
      - ROCM_USE_FLASH_ATTN_V2_TRITON=true
    commands:
      - text-generation-launcher --port 8000
    port: 8000
    # Register the model
    model: meta-llama/Meta-Llama-3.1-70B-Instruct

    # Uncomment to leverage spot instances
    #spot_policy: auto

    resources:
      gpu: MI300X
      disk: 150GB
    ```
    
    </div>

=== "Dev environment"
    Here's an example of a [dev environment](../../docs/concepts/dev-environments.md) using
    [TGI :material-arrow-top-right-thin:{ .external }](https://huggingface.co/docs/text-generation-inference/en/installation_amd){:target="_blank"}'s
    Docker image:

    ```yaml
    type: dev-environment
    name: amd-dev-tgi
    
    image: ghcr.io/huggingface/text-generation-inference:sha-a379d55-rocm
    env:
      - HF_TOKEN
      - ROCM_USE_FLASH_ATTN_V2_TRITON=true
    ide: vscode
    
    # Uncomment to leverage spot instances
    #spot_policy: auto

    resources:
      gpu: MI300X
      disk: 150GB
    ```

!!! info "Docker image"
    Please note that if you want to use AMD, specifying `image` is currently required. This must be an image that includes
    ROCm drivers.

To request multiple GPUs, specify the quantity after the GPU name, separated by a colon, e.g., `MI300X:4`.

Once the configuration is ready, run `dstack apply -f <configuration file>`, and `dstack` will automatically provision the
cloud resources and run the configuration.

??? info "Control plane"
    If you specify `model` when running a service, `dstack` will automatically register the model on
    an OpenAI-compatible endpoint and allow you to use it for chat via the control plane UI.
    
    <img src="https://dstack.ai/static-assets/static-assets/images/dstack-control-plane-model-llama31.png" width="750px" />

## What's next?

1. The examples above demonstrate the use of
[TGI :material-arrow-top-right-thin:{ .external }](https://huggingface.co/docs/text-generation-inference/en/installation_amd){:target="_blank"}. 
AMD accelerators can also be used with other frameworks like vLLM, Ollama, etc., and we'll be adding more examples soon.
2. RunPod is the first cloud provider where dstack supports AMD. More cloud providers will be supported soon as well.
3. Want to give RunPod and `dstack` a try? Make sure you've signed up for [RunPod :material-arrow-top-right-thin:{ .external }](https://www.runpod.io/){:target="_blank"}, 
   then [set up](../../docs/reference/server/config.yml.md#runpod) the `dstack server`. 

> Have questioned or feedback? Join our [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"} 
server.
