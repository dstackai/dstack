---
title: Presets
description: Creating and reusing optimized model inference configurations
---

# Presets

A preset configuration lets you use an agent to create a preset: a validated and optimized model inference configuration. Once created, the preset can be reused to deploy model inference on validated hardware without an agent.

The value of presets comes from combining two fundamental features: agent-driven model inference optimization and the `dstack` [service](services.md) primitive, which can deploy model inference to any cloud, Kubernetes, or on-prem cluster.

> The presets feature is experimental and may change.

??? info "Prerequisites"
    Before using presets, make sure you’ve [installed](../installation.md) the server and CLI, and created a [fleet](fleets.md).

    Creating a preset requires the `claude` CLI to be installed on the machine where you create a preset.

## Create a preset

First, define a preset configuration as a YAML file in your project folder.
The filename must end with `.dstack.yml` (e.g. `.dstack.yml` or `preset.dstack.yml` are both acceptable).

<div editor-title="preset.dstack.yml">

```yaml
type: preset
name: qwen25-7b

# The agent picks a compatible variant of the base model
base: Qwen/Qwen2.5-7B-Instruct

# The number of benchmarked trials
max_trials: 3

env:
  - HF_TOKEN
```

</div>

To create the preset, pass the configuration to the `dstack preset create` command:

<div class="termy">

```shell
$ dstack preset create -f preset.dstack.yml
Create the preset qwen25-7b? [y/n]: y
[2026-07-15 11:32:01] Starting preset creation for Qwen/Qwen2.5-7B-Instruct. Allowed fleets: gpu-fleet.
[2026-07-15 11:41:06] Prototype task qwen25-7b-a1b2c3-2 verified vLLM on an L4:24GB.
[2026-07-15 11:52:06] Final service qwen25-7b-a1b2c3-3 verified with context length 32768.
[2026-07-15 11:52:18] Benchmark via guidellm 0.7.1: 32/32 requests succeeded.
[2026-07-15 11:52:18] Saved preset 8f3a12c4 for Qwen/Qwen2.5-7B-Instruct.
```

</div>

The command executes entirely locally and uses the locally installed `claude` CLI along with `dstack`'s bundled skills. The agent uses a `dstack` task to find the best serving configuration for the available fleet offers, then submits it as a `dstack` service for a final benchmark. The validated preset is saved locally under `~/.dstack/presets`.

You can stop watching with <kbd>Ctrl+C</kbd> at any time. The agent keeps running, and `dstack preset logs -f` follows it again. Resume an interrupted creation with `dstack preset create --resume`:

<div class="termy">

```shell
$ dstack preset create -f preset.dstack.yml --resume a1b2c3d4
```

</div>

!!! info "Claude configuration"
    By default, preset creation uses the existing `claude` login. To use an Anthropic API key instead, set:

    ```shell
    export DSTACK_AGENT_ANTHROPIC_API_KEY=...
    ```

    By default, the agent uses `claude-opus-4-8` and the default `claude` CLI effort. To override them, set:

    ```shell
    export DSTACK_AGENT_ANTHROPIC_MODEL=claude-fable-5
    export DSTACK_AGENT_CLAUDE_EFFORT=high
    ```

    Supported effort levels are `low`, `medium`, `high`, `xhigh`, and `max`.

## Configuration options

### Model

=== "Base"

    Set `base` to let the creation agent select any compatible variant of the base model, including a different precision, quantization, or trusted fork.

    ```yaml
    base: Qwen/Qwen2.5-7B-Instruct
    ```

=== "Repo"

    Set `repo` to deploy an exact model.

    ```yaml
    repo: Qwen/Qwen2.5-7B-Instruct
    ```

### Trials

`max_trials` is required and sets how many benchmarked trials the agent runs before promoting the best one. Set `concurrency` to control the benchmark concurrency.

### Context length

Set `context_length` to require a minimum supported context length.

### Fleets

Set `fleets` to restrict creation and reuse to specific [fleets](fleets.md). Placement properties such as `backends`, `max_price`, and `spot_policy` constrain both creation and reuse too.

### Prompt

Set `prompt` to guide the agent with custom objectives, target metrics, or an experimentation approach. It accepts inline text or a file `path`.

<div editor-title="preset.dstack.yml">

```yaml
prompt: |
  Optimize for the lowest TTFT at concurrency 32. Consider FP8 quantization.
```

</div>

!!! info "Reference"
    The `preset` configuration supports many more options. See the [`.dstack.yml` reference](../reference/dstack.yml/preset.md).

## Apply a preset

To deploy a preset as a service, pass the preset configuration and the preset ID or name to the `dstack preset apply` command:

<div class="termy">

```shell
$ dstack preset apply -f preset.dstack.yml --id qwen35-27b
 Project        main
 User           admin
 Type           service
 Resources      cpu=2.. mem=8GB.. disk=100GB.. gpu=RTXPRO4500:32GB:1..
 Spot policy    on-demand
 Max price      off
 Model          Qwen/Qwen3.5-27B (base)
 Preset         532f3f4b (ctx=8K con=8 387 tok/s TTFT 582ms)

 #  BACKEND           RESOURCES                                         INSTANCE TYPE                  PRICE
 1  runpod (EU-RO-1)  cpu=12 mem=54GB disk=100GB gpu=RTXPRO4500:32GB:1  NVIDIA RTX PRO 4500 Blackwell  $0.74

Submit the run qwen35-27b? [y/n]: y
```

</div>

## Manage presets

### List presets

Use `dstack preset` to list presets:

<div class="termy">

```shell
$ dstack preset list
 BASE               ID        GPU                  BENCHMARK                    STATUS              SUBMITTED     NAME
 Qwen/Qwen2.5-0.5B
                    bc592b38                                                    clauding (0/3)      23 sec ago    qwen05
 Qwen/Qwen3-32B
                    f91d6b60  RTX5090:32GB:1       con=8 576 tok/s TTFT 368ms   verified (10/10)    2 days ago    qwen3-32b
 Qwen/Qwen3.5-27B
                    3c4d5e6f                                                    verifying (3/3)     2 min ago     qwen35-27b-2
                    532f3f4b  RTXPRO4500:32GB:1..  con=8 387 tok/s TTFT 582ms   verified (4/4)      yesterday     qwen35-27b
                    d1c2e12b  RTX5090:32GB:1       con=8 266 tok/s TTFT 2.15s   verified (7/10)     yesterday
```

</div>

Presets are grouped by base model. In-progress creations appear too, with a live status like `clauding` or `verifying`. Pass `-w` to watch in realtime. Pass `-v` to include validation resources and all benchmark metrics, or `--json` for complete preset objects. Filter with `--base` or `--repo`.

### Delete presets

Delete a preset by ID or name, or all presets for a base model with `--base`:

<div class="termy">

```shell
$ dstack preset delete 8f3a12c4
```

</div>

For command options and agent settings, see the [`dstack preset` CLI reference](../reference/cli/dstack/preset.md).

> Presets are experimental, and we’d love your feedback. Report bugs and request features on [GitHub](https://github.com/dstackai/dstack/issues), and ask questions on [Discord](https://discord.gg/u8SmfwPpMd).

!!! info "What's next?"
    1. Learn how dstack [services](services.md) work
    2. Learn how to configure [fleets](fleets.md)
