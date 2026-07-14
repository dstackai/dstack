---
title: Endpoints
description: Creating and reusing optimized model inference recipes
---

# Endpoints

An endpoint configuration is a new `dstack` feature that lets you use an agent to create presets: validated and optimized model inference endpoint recipes. Once a preset is created, it can be reused to deploy model inference on validated hardware without an agent.

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
```

</div>

This command executes entirely locally and uses the locally installed `claude` CLI along with `dstack`'s bundled skills. The agent uses a `dstack` task to find the best serving recipe matching the available fleet offers. Once the recipe is found, it submits a `dstack` service for a final benchmark. The validated recipe is saved locally under `~/.dstack/presets`.

??? info "Claude authorization"
    Preset creation supports two Claude authorization methods. To use an Anthropic API key, set:

    ```shell
    export DSTACK_AGENT_ANTHROPIC_API_KEY=...
    ```

    If you are already logged in with `claude`, use the existing authorization instead:

    ```shell
    export DSTACK_AGENT_CLAUDE_USE_EXISTING_AUTH=1
    ```

    These options are mutually exclusive.

## List presets

Use `dstack endpoint preset` to list existing presets:

<div class="termy">

```shell
$ dstack endpoint preset list
 MODEL                       GPU                    CONTEXT  BENCHMARK
 Qwen/Qwen2.5-7B-Instruct
    recipe=8f3a12c4          nvidia:16GB..24GB:1.. 32K      L4:24GB:1 n=32 c=4 1K->128 464 tok/s TTFT p50=312ms
```

</div>

Each base model corresponds to one preset. A preset may contain multiple recipes built for specific hardware. Each recipe includes benchmark data.

Pass `-v` to include validation resources and all benchmark metrics, or `--json`
to output complete recipe objects.

## Apply a preset

To deploy a preset as a service, pass the endpoint configuration to the `dstack endpoint preset apply` command:

<div class="termy">

```shell
$ dstack endpoint preset apply -f endpoint.dstack.yml
```

</div>

If you don't pass `--recipe ID` (or specify it in the endpoint configuration), `dstack` automatically picks one of the recipes that matches the available fleet offers.

If a recipe matches, `dstack` deploys it as a service.

## Delete a preset

You can delete a specific recipe or the entire preset.

<div class="termy">

```shell
dstack endpoint preset delete --recipe 8f3a12c4
```

</div>

To delete the entire preset and all its recipes, pass the base model:

<div class="termy">

```shell
dstack endpoint preset delete Qwen/Qwen2.5-7B-Instruct
```

</div>

For command options and agent settings, see the
[`dstack endpoint` CLI reference](../reference/cli/dstack/endpoint.md).

!!! info "What's next?"
    1. Learn how dstack [services](services.md) work
    2. Learn how to configure [fleets](fleets.md)
