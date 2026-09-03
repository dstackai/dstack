---
title: Presets
description: Creating and reusing optimized model inference configurations
---

# Presets

Presets offer a toolkit that streamlines agent-based model inference optimization and a portable format to deploy the optimized inference endpoint to any cloud, Kubernetes cluster, or on-prem fleet.

> The presets feature is experimental and may change.

??? info "Prerequisites"
    Before using presets, make sure you’ve [installed](../installation.md) the server and CLI, and created a [fleet](fleets.md).

    Creating a preset requires the `claude` CLI to be installed on the machine where you create a preset.

## Apply a configuration

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

To create the preset, pass the configuration to the `dstack apply` command:

<div class="termy">

```shell
$ dstack apply -f preset.dstack.yml --fleet b200-fleet
Create the preset dsv4-flash? [y/n]: y
[2026-08-04 11:38:34] Starting preset creation for deepseek-ai/DeepSeek-V4-Flash. Allowed fleets: b200-fleet.
[2026-08-04 12:31:19] Trial 3 switched from vLLM to SGLang: 319 tok/s per user, 2.2x the baseline.
[2026-08-04 13:04:52] Final service dsv4-flash-c83375b4-4 verified with context length 1048576.
[2026-08-04 13:12:07] Benchmark via sglang.bench_serving: 32/32 requests succeeded.
```

</div>

> It's highly recommended to specify the exact hardware you want the preset to use, so that the
> optimization is done against that hardware. Point `dstack apply` to a fleet configured
> correspondingly, via `fleets` inside the preset configuration or via `--fleet` in the CLI.

The command executes entirely locally and uses the locally installed `claude` CLI along with `dstack`'s bundled skills. The agent uses a `dstack` task to find the best serving configuration for the available fleet offers, then submits it as a `dstack` service for a final benchmark.

You can stop watching with `Ctrl`+`C` at any time. The agent keeps running, and `dstack preset logs -f` follows it again. Resume an interrupted creation with `dstack preset resume`:

<div class="termy">

```shell
$ dstack preset resume a1b2c3d4
```

</div>

When resuming, the configuration and constraints are read from the original session. To change any of them, create a new preset.

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

Alternatively, pass `--fleet` to `dstack apply`.

> Profile settings such as `spot_policy`, `max_price`, and `backends` are ignored during preset
> creation. Configure them on the fleet instead.

### Model

=== "Base"

    Set `base` to let the agent select any compatible variant of the base model, including a different precision, quantization, or trusted fork.

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

Alternatively, pass `--previous` (repeatable) to `dstack apply`.

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

## Push and pull a preset

To share a preset, push it to the registry:

<div class="termy">

```shell
$ dstack preset push dsv4-flash-b200 main/dsv4-flash-b200
OK
```

</div>

Pull it wherever you want to use it:

<div class="termy">

```shell
$ dstack preset pull main/dsv4-flash-b200
OK
```

</div>

Push shares everything needed to deploy the preset. The prompt and trials that produced it stay on your machine.

A pulled preset works like any other, and is named `<project>/<name>`:

<div class="termy">

```shell
$ dstack preset list -a
 NAME                    ID        BASE                           CONSTRAINTS      BENCHMARK                       STATUS          SUBMITTED
 main/dsv4-flash-b200    8f065dde  deepseek-ai/DeepSeek-V4-Flash  io=10K/1.5K c=1  tps/user=309 ttft=213ms ctx=1M  pulled          2 min ago
 qwen35-pro6000          092c792b  Qwen/Qwen3.5-397B-A17B         io=8K/1K c=64    tps/user=19.6 ttft=3.43s ctx=32K  verified (7)  3 days ago
```

</div>

Pushing the same name again moves the name to the new preset. The previous one stays available as `<project>/<id>`.

### Registry

Presets are pushed to and pulled from the registry hosted at [dstack Sky](https://sky.dstack.ai). To share a preset, create a project there, add the people you want to share it with, and push the preset to that project. To push or pull a preset from a project, you have to be its member.

A self-hosted registry is part of [dstack Factory](https://calendly.com/dstackai/discovery-call){ target="_blank" }.

## Export a preset

To deploy a preset, export it as a service configuration with `dstack preset export`:

<div class="termy">

```shell
$ dstack preset export c83375b4 -f qwen.dstack.yml
OK
```

</div>

The command writes the service configuration along with any files it references, such as patches. The service is named after the preset; pass `-n` to override. Optionally, set a [gateway](gateways.md) in the exported configuration, then submit it with `dstack apply`:

<div class="termy">

```shell
$ dstack apply -f qwen.dstack.yml
 Project        main
 User           admin
 Type           service
 Resources      cpu=8.. mem=64GB.. disk=500GB gpu=B200:180GB:2
 Spot policy    on-demand
 Max price      off
 Retry policy   off
 Idle duration  5m
 Max duration   off

 #  BACKEND           RESOURCES                                    INSTANCE TYPE  PRICE
 1  runpod (US-CA-2)  cpu=48 mem=502GB disk=500GB gpu=B200:180GB:2  NVIDIA B200    $11.78

Submit the run dsv4-flash? [y/n]: y
```

</div>

## Manage presets

### Monitor presets

While a preset is being created, you can watch the progress of its trials and what the agent is doing.

The `dstack preset logs` command shows the progress log: one line per milestone, such as a trial finishing or the final service being verified. Pass `-f` to follow a running creation:

<div class="termy">

```shell
$ dstack preset logs -f c83375b4
```

</div>

!!! info "Traces"
    The agent subprocess writes real-time traces to `~/.dstack/presets/<id>/trace.jsonl`: the agent's messages and every tool call with its result. Traces are the main way to analyze a session in depth — see [Protips](#protips).

### List presets

Use `dstack preset` to list presets:

<div class="termy">

```shell
$ dstack preset list
 NAME              ID        BASE                           CONSTRAINTS      BENCHMARK                                STATUS          SUBMITTED
 dsv4-flash-b200   c83375b4  deepseek-ai/DeepSeek-V4-Flash  io=10K/1.5K c=1  tps/user=309 ttft=213ms ctx=1M  ▂▁██▇  trialing (5/5)  2 min ago
```

</div>

By default, `dstack preset` shows creations that are still running, or the most recent one if none are. Pass `-a` to show every preset, or `-n` to show the last N:

<div class="termy">

```shell
$ dstack preset list -a
 NAME               ID        BASE                            CONSTRAINTS      BENCHMARK                                     STATUS          SUBMITTED
 dsv4-flash-b200    c83375b4  deepseek-ai/DeepSeek-V4-Flash   io=10K/1.5K c=1  tps/user=309 ttft=213ms ctx=1M   ▂▁██▇     trialing (5/5)  2 min ago
 qwen35-pro6000     092c792b  Qwen/Qwen3.5-397B-A17B          io=8K/1K c=64    tps/user=19.6 ttft=3.43s ctx=32K ▁▂▅▇█··   verified (7)    3 days ago
 qwen36-pro4500     9ab0fa65  Qwen/Qwen3.6-27B                io=1K/1K c=8     tps/user=57.1 ttft=499ms ctx=128K ▁▄██▆·█  verified (7)    4 days ago
 qwen3-32b-5090     f91d6b60  Qwen/Qwen3-32B                  io=1K/512 c=8    tps/user=85.8 ttft=368ms ctx=32K ▁▁▅▅▄▅▇▄▇█ verified (10)  2 weeks ago
```

</div>

The `CONSTRAINTS` column is what the creation was asked for, and `BENCHMARK` is the best trial so far. `tps/user` is the steady decode rate, measured as one second divided by the mean time per output token, so it excludes the time to the first token.

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

## Protips

Under the hood, presets run an agent as a subprocess, using the local `claude` CLI. This process writes a real-time trace to `~/.dstack/presets/<id>/trace.jsonl`. The subprocess is launched with a built-in harness: how to run trials, submit runs, benchmark, verify presets, and use `dstack`.

At the same time, it's recommended to create presets using your own agent — either via a CLI such as Claude Code, or inside your IDE. Your agent helps you design the preset configuration, formulate hypotheses, and — most importantly — analyze the session's traces as well as the trial results (stored under `~/.dstack/presets/<id>/trials/<n>/trial.json`), to decide what the next session can be and what instructions to give it via `prompt`.

> To help your agent use `dstack` and presets, install the [`dstack`](https://skills.sh/dstackai/dstack/dstack)
> and [`dstack-presets`](https://skills.sh/dstackai/dstack/dstack-presets) skills with `npx skills add dstackai/dstack`.

## Limitations

* Currently, the agent doesn't upload compiled binaries anywhere; patches compile at runtime
* The registry doesn't support public presets (coming soon)
* Doesn't support ranges for `concurrency`

> Report bugs and request features on [GitHub](https://github.com/dstackai/dstack/issues), and ask questions on [Discord](https://discord.gg/u8SmfwPpMd).

!!! info "What's next?"
    1. Learn how dstack [services](services.md) work
    2. Learn how to configure [fleets](fleets.md)
