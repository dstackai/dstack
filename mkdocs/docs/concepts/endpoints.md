---
title: Endpoints
description: Creating and reusing optimized model inference endpoint configurations
---

# Endpoints

An endpoint configuration lets you use an agent to create a preset: a validated and optimized model inference configuration. Once created, the preset can be reused to deploy model inference on validated hardware without an agent.

The value of presets comes from combining two fundamental features: agent-driven model inference optimization and the `dstack` [service](services.md) primitive, which can deploy model inference to any cloud, Kubernetes, or on-prem cluster.

> The endpoints feature is experimental and may change.

??? info "Prerequisites"
    Before using endpoint presets, make sure you’ve [installed](../installation.md) the server and CLI, and created a [fleet](fleets.md).

    Creating an endpoint preset requires the `claude` CLI to be installed on the machine where you create a preset.

## Define an endpoint

Before you can create or reuse an endpoint preset, you first have to define an endpoint configuration. The filename must end with `.dstack.yml`.

<div editor-title="endpoint.dstack.yml">

```yaml
type: endpoint
name: qwen25-7b

model:
  base: Qwen/Qwen2.5-7B-Instruct

env:
  - HF_TOKEN
```

</div>

Since `base` is specified, the preset can use any compatible variant of the base model, including a different precision, quantization, or trusted fork.

If you want to deploy an exact model, set `model` directly to the repo of that model:

<div editor-title="endpoint.dstack.yml">

```yaml
type: endpoint
name: qwen25-7b

model: Qwen/Qwen2.5-7B-Instruct

env:
  - HF_TOKEN
```

</div>

Set `context_length` to require a minimum context length. Placement properties,
including `fleets`, `backends`, `max_price`, and `spot_policy`, constrain both
creation and reuse. Environment variables such as `HF_TOKEN` can be passed
through `env`.

See the [reference](../reference/dstack.yml/endpoint.md) for all supported configuration options.

## Create a preset

To create a preset, pass the configuration file to the `dstack endpoint preset create` command:

<div class="termy">

```shell
$ dstack endpoint preset create -f endpoint.dstack.yml
[2026-07-15 11:32:01] Starting endpoint preset creation for Qwen/Qwen2.5-7B-Instruct. Allowed fleets: gpu-fleet.
[2026-07-15 11:41:06] Prototype task qwen25-7b-a1b2c3-2 verified vLLM on an L4:24GB.
[2026-07-15 11:52:06] Final service qwen25-7b-a1b2c3-3 verified with context length 32768.
[2026-07-15 11:52:18] Benchmark via guidellm 0.7.1: 32/32 requests succeeded.
[2026-07-15 11:52:18] Saved endpoint preset 8f3a12c4 for Qwen/Qwen2.5-7B-Instruct.
```

</div>

This command executes entirely locally and uses the locally installed `claude` CLI along with `dstack`'s bundled skills. The agent uses a `dstack` task to find the best serving configuration for the available fleet offers. It then submits the configuration as a `dstack` service for a final benchmark. The validated preset is saved locally under `~/.dstack/presets`.

??? info "Claude configuration"
    Preset creation supports two Claude authorization methods. To use an Anthropic API key, set:

    ```shell
    export DSTACK_AGENT_ANTHROPIC_API_KEY=...
    ```

    If you are already logged in with `claude`, use the existing authorization instead:

    ```shell
    export DSTACK_AGENT_CLAUDE_USE_EXISTING_AUTH=1
    ```

    These options are mutually exclusive.

    By default, the agent uses `claude-opus-4-8` and the default `claude` CLI effort. To override them, set:

    ```shell
    export DSTACK_AGENT_ANTHROPIC_MODEL=claude-fable-5
    export DSTACK_AGENT_CLAUDE_EFFORT=high
    ```

    Supported effort levels are `low`, `medium`, `high`, `xhigh`, and `max`.

## List presets

Use `dstack endpoint preset` to list existing presets:

<div class="termy">

```shell
$ dstack endpoint preset list
 MODEL                     GPU                    CONTEXT  BENCHMARK
 Qwen/Qwen2.5-7B-Instruct
    preset=8f3a12c4        nvidia:16GB..24GB:1..  32K      concurrency=1 464 tok/s TTFT 312ms
```

</div>

Presets are grouped by base model. Each preset contains an optimized serving configuration for a specific model variant, along with its hardware requirements, validation, and benchmark data.

Pass `-v` to include validation resources and all benchmark metrics, or `--json`
to output complete preset objects.

## Apply a preset

To deploy a preset as a service, pass the endpoint configuration to the `dstack endpoint preset apply` command:

<div class="termy">

```shell
$ dstack endpoint preset apply -f endpoint.dstack.yml
 Model          Qwen/Qwen2.5-7B-Instruct (base)
 Preset         8f3a12c4 (context=32K, concurrency=1 464 tok/s TTFT 312ms)

 #  BACKEND            RESOURCES                      INSTANCE TYPE     PRICE
 1  runpod (CA-MTL-1)  cpu=9 mem=50GB disk=200GB      NVIDIA RTX A5000  $0.27
                       gpu=A5000:24GB:1
 2  runpod (CA-MTL-1)  cpu=9 mem=50GB disk=200GB      NVIDIA RTX A5000  $0.27
                       gpu=A5000:24GB:1 (spot)
 3  runpod (US-IL-1)   cpu=12 mem=25GB disk=200GB     NVIDIA RTX A5000  $0.27
                       gpu=A5000:24GB:1
    ...
 Shown 3 of 4 offers, $0.27max

Submit the run qwen25-7b? [y/n]: y
```

</div>

If you don't pass `--preset ID` or specify `preset` in the endpoint configuration, `dstack` automatically selects a matching preset based on the available fleet offers. It then deploys the preset as a service.

## Delete presets

You can delete a specific preset by ID or all presets for a base model.

<div class="termy">

```shell
$ dstack endpoint preset delete --preset 8f3a12c4
```

</div>

To delete all presets for a base model, pass `--model`:

<div class="termy">

```shell
$ dstack endpoint preset delete --model Qwen/Qwen2.5-7B-Instruct
```

</div>

For command options and agent settings, see the
[`dstack endpoint` CLI reference](../reference/cli/dstack/endpoint.md).

!!! info "What's next?"
    1. Learn how dstack [services](services.md) work
    2. Learn how to configure [fleets](fleets.md)
