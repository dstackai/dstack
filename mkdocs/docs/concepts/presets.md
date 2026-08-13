---
title: Presets
description: Creating and reusing optimized model inference configurations
---

# Presets

A preset configuration lets you use an agent to create a preset: a verified and optimized model inference configuration. Once created, the preset can be reused to deploy model inference on verified hardware without an agent.

The value of presets comes from combining two fundamental features: agent-driven model inference optimization and the `dstack` [service](services.md) primitive, which can deploy model inference to any cloud, Kubernetes, or on-prem cluster.

To get the best performance for the given model, hardware, and other constraints, the agent selects the serving framework, quantization, and serving parameters, and can patch the framework's source code, generate custom kernels, and patch drivers.

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
name: dsv4-flash

# The agent picks a compatible variant of the base model
base: deepseek-ai/DeepSeek-V4-Flash

# The number of benchmarked trials
trials: 5

# The requirements the preset must meet (time to first token is in milliseconds)
min_context_length: 1048576
max_ttft: 675

# The number of simultaneous requests every benchmark uses
concurrency: 1

# The request shape every benchmark uses (defaults to 1024 and 1024)
input_tokens: 10000
output_tokens: 1500

# The environment variables the agent may pass to runs
env:
  - HF_TOKEN
```

</div>

To create the preset, pass the configuration to the `dstack preset create` command:

<div class="termy">

```shell
$ dstack preset create -f preset.dstack.yml --fleet b200-fleet
Create the preset dsv4-flash? [y/n]: y
[2026-08-04 11:38:34] Starting preset creation for deepseek-ai/DeepSeek-V4-Flash. Allowed fleets: b200-fleet.
[2026-08-04 12:31:19] Trial 3 switched from vLLM to SGLang: 319 tok/s per user, 2.2x the baseline.
[2026-08-04 13:04:52] Final service dsv4-flash-c83375b4-4 verified with context length 1048576.
[2026-08-04 13:12:07] Benchmark via sglang.bench_serving: 32/32 requests succeeded.
```

</div>

> It's highly recommended to specify the exact hardware you want the preset to use, so that the
> optimization is done against that hardware. Point `dstack preset create` to a fleet configured
> correspondingly, via `fleets` inside the preset configuration or via `--fleet` in the CLI.

The command executes entirely locally and uses the locally installed `claude` CLI along with `dstack`'s bundled skills. The agent uses a `dstack` task to find the best serving configuration for the available fleet offers, then submits it as a `dstack` service for a final benchmark.

You can stop watching with `Ctrl`+`C` at any time. The agent keeps running, and `dstack preset logs -f` follows it again. Resume an interrupted creation with `dstack preset create --resume`:

<div class="termy">

```shell
$ dstack preset create -f preset.dstack.yml --resume a1b2c3d4
```

</div>

When resuming, the constraints are read from the original session, not from the configuration file. Editing them and resuming has no effect. To change any of them, create a new preset.

To stop a creation and its runs, use `dstack preset stop`.

??? info "Claude configuration"
    By default, preset creation uses the existing `claude` login. To use an Anthropic API key instead, set:

    ```shell
    export DSTACK_AGENT_ANTHROPIC_API_KEY=...
    ```

    By default, the agent uses `claude-opus-4-8`. It doesn't set an effort level, so the `claude` CLI default applies. To override them, set:

    ```shell
    export DSTACK_AGENT_ANTHROPIC_MODEL=claude-opus-5
    export DSTACK_AGENT_CLAUDE_EFFORT=max
    ```

    Supported effort levels are `low`, `medium`, `high`, `xhigh`, and `max`.

??? info "Presets directory"
    The verified presets are saved locally under `~/.dstack/presets`, and `dstack preset` reads them from there. Presets aren't stored on the server.

## Configuration options

### Fleets

Set `fleets` to restrict creation and reuse to specific [fleets](fleets.md). It's highly recommended to specify a fleet with exactly the hardware that you'd like the preset to use.

Alternatively, pass `--fleet` to `dstack preset create` or `dstack preset apply`.

> Profile settings such as `spot_policy`, `max_price`, and `backends` are ignored during preset
> creation. Configure them on the fleet instead.

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

### Previous sessions

Set `previous` to a list of preset IDs to give the agent the results of earlier creation sessions. It analyzes what they tried and how it worked, and aims to improve on them instead of rediscovering it.

<div editor-title="preset.dstack.yml">

```yaml
previous:
  - c83375b4
```

</div>

Alternatively, pass `--previous` (repeatable) to `dstack preset create`.

### Prompt

Set `prompt` to steer what the agent explores: which frameworks or model variants to try, or how deep to go before settling. It accepts inline text or a file `path`. Constraints such as `concurrency` and `max_ttft` can't be changed this way.

<div editor-title="preset.dstack.yml">

```yaml
prompt: |
  Profile the engine before each trial and report how far it is from the
  memory-bandwidth roofline. While that gap is large, prefer patching the
  serving framework over tuning flags.
```

</div>

### Dataset

The requests every benchmark measures.

=== "Random"

    By default, benchmarks use synthetic prompts shaped by `input_tokens` and `output_tokens`. Set `shared_prefix_tokens` to make part of every request identical, such as a system prompt or conversation history, so the serving framework can serve it from its prefix cache. It must be less than `input_tokens`.

    ```yaml
    input_tokens: 8192
    output_tokens: 1024

    # Roughly 90% of prompt tokens can be served from cache
    shared_prefix_tokens: 7360
    ```

=== "Custom"

    Set `dataset` to benchmark on real text instead: a dataset the benchmark tool supports, or a Hugging Face dataset ID.

    ```yaml
    dataset: sharegpt
    ```

    The dataset provides the requests, so `input_tokens`, `output_tokens`, and `shared_prefix_tokens` can't be set with it, and the preset records the measured means. A gated dataset requires `HF_TOKEN` in `env`.

### Baseline

By default, the first trial is a baseline: the agent serves the model the way the chosen serving framework recommends, without tuning it for performance. Later trials are optimization attempts. Set `baseline: false` to make every trial an optimization attempt.

When the session builds on `previous`, the baseline trial reproduces the best comparable previous result instead, to confirm it still holds before optimizing further.

!!! info "Reference"
    The `preset` configuration supports many more options. See the [`.dstack.yml` reference](../reference/dstack.yml/preset.md).

## Apply a preset

To deploy a preset as a service, pass the preset configuration and the preset ID to the `dstack preset apply` command:

<div class="termy">

```shell
$ dstack preset apply -f preset.dstack.yml --id c83375b4
 Project        main
 User           admin
 Type           service
 Resources      cpu=8.. mem=64GB.. disk=500GB gpu=B200:180GB:2
 Spot policy    on-demand
 Max price      off
 Retry policy   off
 Idle duration  5m
 Max duration   off
 Model          deepseek-ai/DeepSeek-V4-Flash (base)
 Preset         c83375b4 (io=10000/1500 conc=1 tok/s/user=309 tok/s=296 ttft=213ms ctx=1M)

 #  BACKEND           RESOURCES                                    INSTANCE TYPE  PRICE
 1  runpod (US-CA-2)  cpu=48 mem=502GB disk=500GB gpu=B200:180GB:2  NVIDIA B200    $11.78

Submit the run dsv4-flash? [y/n]: y
```

</div>

## Manage presets

### List presets

Use `dstack preset` to list presets:

<div class="termy">

```shell
$ dstack preset list
 ID        BASE                           GPU           CONSTRAINTS           BENCHMARK                                STATUS          SUBMITTED
 c83375b4  deepseek-ai/DeepSeek-V4-Flash  B200:180GB:2  io=10000/1500 conc=1  tok/s/user=309 ttft=213ms ctx=1M  ▂▁██▇  trialing (5/5)  2 min ago
```

</div>

By default, `dstack preset` shows creations that are still running, or the most recent one if none are. Pass `-a` to show every preset, or `-n` to show the last N:

<div class="termy">

```shell
$ dstack preset list -a
 ID        BASE                            GPU              CONSTRAINTS           BENCHMARK                                     STATUS          SUBMITTED
 c83375b4  deepseek-ai/DeepSeek-V4-Flash   B200:180GB:2     io=10000/1500 conc=1  tok/s/user=309 ttft=213ms ctx=1M   ▂▁██▇     trialing (5/5)  2 min ago
 092c792b  Qwen/Qwen3.5-397B-A17B          RTXPRO6000:4     io=8K/1K conc=64      tok/s/user=19.6 ttft=3.43s ctx=32K ▁▂▅▇█··   verified (7)    3 days ago
 9ab0fa65  Qwen/Qwen3.6-27B                RTXPRO4500:1     io=1K/1K conc=8       tok/s/user=57.1 ttft=499ms ctx=128K ▁▄██▆·█  verified (7)    4 days ago
 f91d6b60  Qwen/Qwen3-32B                  RTX5090:32GB:1   io=1K/512 conc=8      tok/s/user=85.8 ttft=368ms ctx=32K ▁▁▅▅▄▅▇▄▇█ verified (10)  2 weeks ago
```

</div>

The `CONSTRAINTS` column is what the creation was asked for, and `BENCHMARK` is the best trial so far. `tok/s/user` is the steady decode rate, measured as one second divided by the median time per output token, so it excludes the time to the first token.

The glyphs after the benchmark are one per trial: height is throughput, a yellow bar is a trial whose benchmark broke a constraint, and a red `·` is one that produced no benchmark at all. The shape shows whether a run converged or wandered.

Pass `-w` to watch in realtime, `-v` for more detail, or `--json` for complete preset objects. Filter with `--base` or `--repo`.

### Delete presets

Delete a preset by ID or name, or all presets for a base model with `--base`:

<div class="termy">

```shell
$ dstack preset delete c83375b4
```

</div>

!!! info "Reference"
    For command options and agent settings, see the [`dstack preset` CLI reference](../reference/cli/dstack/preset.md).

## Troubleshooting

To trace the agent's activity, pass `--debug` to `dstack preset create`:

<div class="termy">

```shell
$ dstack preset create -f preset.dstack.yml --debug
```

</div>

The trace is written to `~/.dstack/presets/<id>/trace.jsonl` while the session runs. It contains the agent's messages and every tool call with its result.

## Limitations

* Currently, the agent doesn't upload compiled binaries anywhere; patches compile at runtime
* Doesn't support PD disaggregation (coming soon)
* Presets are saved locally (a preset registry is coming soon)
* Doesn't support ranges for `concurrency`

> Report bugs and request features on [GitHub](https://github.com/dstackai/dstack/issues), and ask questions on [Discord](https://discord.gg/u8SmfwPpMd).

!!! info "What's next?"
    1. Learn how dstack [services](services.md) work
    2. Learn how to configure [fleets](fleets.md)
