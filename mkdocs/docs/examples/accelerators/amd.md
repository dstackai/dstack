---
title: AMD
description: Running dev environments, tasks, and services on AMD GPUs
---

# AMD

`dstack` natively supports AMD GPUs. This page covers the basics of setting up
fleets, running inference, training, and dev environments on AMD GPUs.

## Fleets

`dstack` supports native cloud provisioning, and can also work with existing
Kubernetes clusters or vanilla bare-metal hosts.

=== "Clouds"

    `dstack` supports native provisioning of VMs with AMD GPUs across a number
    of clouds, including
    [AMD Developer Cloud](../../concepts/backends.md#amd-developer-cloud) and
    [Hot Aisle](../../concepts/backends.md#hot-aisle). More cloud support is
    coming soon.

    To provision compute in these clouds, configure the corresponding
    [backend](../../concepts/backends.md) and create a
    [backend fleet](../../concepts/fleets.md).

=== "Kubernetes"

    To use `dstack` with existing Kubernetes cluster(s), configure the
    [`kubernetes` backend](../../concepts/backends.md#kubernetes) and point it
    to your kubeconfig file. Then create a
    [backend fleet](../../concepts/fleets.md).

=== "SSH fleets"

    If you'd like `dstack` to use a cluster or machine that is already
    provisioned and that you have access to, create an
    [SSH fleet](../../concepts/fleets.md).

!!! info "Cluster placement"
    For multi-node workloads, the fleet must set `placement` to `cluster`. For
    Kubernetes and SSH fleets, the network must be properly configured.

    > To test whether the fleet is properly configured, run the
    > [RCCL tests via a distributed task](../clusters/nccl-rccl-tests.md).

Once a fleet is created, you can run dev environments, tasks, and services.

## Inference

Here are examples of a [service](../../concepts/services.md) that deploys
`Qwen/Qwen3.6-27B` on AMD MI300X GPUs using
[SGLang](https://github.com/sgl-project/sglang) and
[vLLM](https://docs.vllm.ai/en/latest/).

=== "SGLang"

    <div editor-title="service.dstack.yml">

    ```yaml
    type: service
    name: qwen36-sglang-amd

    image: lmsysorg/sglang:v0.5.10-rocm720-mi30x

    commands:
      - |
        sglang serve \
          --model-path Qwen/Qwen3.6-27B \
          --host 0.0.0.0 \
          --port 30000 \
          --tp $DSTACK_GPUS_NUM \
          --reasoning-parser qwen3 \
          --mem-fraction-static 0.8 \
          --context-length 262144

    port: 30000
    model: Qwen/Qwen3.6-27B

    volumes:
      - instance_path: /root/.cache
        path: /root/.cache
        optional: true

    resources:
      cpu: 52..
      memory: 896GB..
      shm_size: 16GB
      disk: 450GB..
      gpu: MI300X:4..
    ```

    </div>

    !!! info "PD disaggregation"
        To run SGLang with prefill and decode workers on an interconnected
        cluster of AMD GPU instances, see the
        [SGLang PD disaggregation](../inference/sglang.md#pd-disaggregation)
        example.

        For multi-node PD disaggregation, the fleet must set `placement` to
        `cluster` and have a proper interconnect. See the cluster placement note
        above.

=== "vLLM"

    <div editor-title="service.dstack.yml">

    ```yaml
    type: service
    name: qwen36-vllm-amd

    image: vllm/vllm-openai-rocm:v0.19.1

    commands:
      - |
        vllm serve Qwen/Qwen3.6-27B \
          --host 0.0.0.0 \
          --port 8000 \
          --tensor-parallel-size $DSTACK_GPUS_NUM \
          --max-model-len 262144 \
          --reasoning-parser qwen3

    port: 8000
    model: Qwen/Qwen3.6-27B

    volumes:
      - instance_path: /root/.cache
        path: /root/.cache
        optional: true

    resources:
      cpu: 52..
      memory: 896GB..
      shm_size: 16GB
      disk: 450GB..
      gpu: MI300X:4..
    ```

    </div>

Use the [`dstack apply`](../../reference/cli/dstack/apply.md) command to apply
any configuration, including services, tasks, dev environments, and fleets.

<div class="termy">

```shell
$ dstack apply -f service.dstack.yml
```

</div>

## Training

Below is a [task](../../concepts/tasks.md) that fine-tunes a small language
model using the official
[Transformers causal language modeling example](https://github.com/huggingface/transformers/tree/main/examples/pytorch/language-modeling)
on AMD GPUs.

<div editor-title="train.dstack.yml">

```yaml
type: task
name: amd-qwen3-train

image: rocm/pytorch:latest

commands:
  - git clone --depth 1 https://github.com/huggingface/transformers.git
  - pip install -e ./transformers -r transformers/examples/pytorch/language-modeling/requirements.txt
  - |
    torchrun --standalone --nproc-per-node $DSTACK_GPUS_PER_NODE \
      transformers/examples/pytorch/language-modeling/run_clm.py \
      --model_name_or_path Qwen/Qwen3-0.6B-Base \
      --dataset_name Salesforce/wikitext \
      --dataset_config_name wikitext-2-raw-v1 \
      --do_train \
      --per_device_train_batch_size 1 \
      --gradient_accumulation_steps 8 \
      --max_steps 10 \
      --block_size 512 \
      --learning_rate 2e-5 \
      --bf16 \
      --logging_steps 1 \
      --output_dir /tmp/qwen3-clm

resources:
  gpu: MI300X:4..
  disk: 100GB..
```

</div>

!!! info "Distributed tasks"
    To run training across multiple nodes, use
    [distributed tasks](../../concepts/tasks.md#distributed-tasks). Distributed
    tasks may run on a cluster; in that case, the fleet must set `placement` to
    `cluster` and have a proper interconnect. See the cluster placement note
    above.

## Dev environments

Here's an example of a [dev environment](../../concepts/dev-environments.md)
that can be accessed via your desktop IDE.

<div editor-title=".dstack.yml">

```yaml
type: dev-environment
name: amd-vscode

image: rocm/dev-ubuntu-24.04

ide: vscode

resources:
  gpu: MI300X:1
```

</div>

## Docker image

> If you'd like a run to use AMD GPUs, make sure to specify `image`. The image
> should include a ROCm runtime compatible with the AMD GPUs and the packages
> your workload needs.

## Metrics

Run and job [metrics](../../concepts/metrics.md) include CPU, memory, and GPU
usage. They are available in the UI and via the CLI:

<div class="termy">

```shell
$ dstack metrics &lt;run name&gt;
```

</div>

> AMD GPU metrics require `amd-smi` to be available in the run image. If it
> isn't present, GPU metrics may be unavailable.

## What's next?

1. Browse the dedicated [SGLang](../inference/sglang.md)
   and [vLLM](../inference/vllm.md) examples, plus the
   [Qwen 3.6](../models/qwen36.md) model page.
2. For multi-node inference, see
   [SGLang PD disaggregation](../inference/sglang.md#pd-disaggregation).
3. For cluster validation, run
   [NCCL/RCCL tests](../clusters/nccl-rccl-tests.md).
4. Check [dev environments](../../concepts/dev-environments.md),
   [tasks](../../concepts/tasks.md), [services](../../concepts/services.md),
   [fleets](../../concepts/fleets.md), and
   [backends](../../concepts/backends.md).
