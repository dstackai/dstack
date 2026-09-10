# dstack preset

The `dstack preset` commands create, list, export, and delete local
[presets](../../../concepts/presets.md), and push them to and pull them from a
registry.

The commands that take a preset — `get`, `export`, and `delete` — accept its ID
or name. A pulled preset's name includes the project it came from, e.g.
`main/qwen38-27b-mi300x`.

## dstack preset list

The `dstack preset list` command lists locally stored presets.

##### Usage

<div class="termy">

```shell
$ dstack preset list --help
#GENERATE#
```

</div>

## dstack preset create

> Deprecated: pass a preset configuration to [`dstack apply`](apply.md) instead.

The `dstack preset create` command uses an agent to create and save a
verified preset from a preset configuration.

##### Usage

<div class="termy">

```shell
$ dstack preset create --help
#GENERATE#
```

</div>

##### Agent settings

Preset creation uses the existing `claude` login unless
`DSTACK_AGENT_ANTHROPIC_API_KEY` is set.

| Variable | Description |
| --- | --- |
| `DSTACK_AGENT_ANTHROPIC_API_KEY` | Anthropic API key used by the agent. |
| `DSTACK_AGENT_CLAUDE_PATH` | `claude` executable name or path. Defaults to `claude` from `PATH`. |
| `DSTACK_AGENT_ANTHROPIC_MODEL` | Claude model used by the agent. If unset, the `claude` CLI's built-in default is used. |
| `DSTACK_AGENT_CLAUDE_EFFORT` | Claude effort level: `low`, `medium`, `high`, `xhigh`, or `max`. If unset, the `claude` CLI default is used. |

Agent progress is written to `agent.log` under `~/.dstack/presets/<preset-id>/`,
alongside the effective configuration (`preset.dstack.yml`), the recorded
trials, the agent prompt (`prompt.md`), and the real-time trace
(`trace.jsonl`).

## dstack preset logs

The `dstack preset logs` command shows a preset creation's log. Pass `-f` to
re-follow a detached or running creation to completion.

##### Usage

<div class="termy">

```shell
$ dstack preset logs --help
#GENERATE#
```

</div>

## dstack preset stop

The `dstack preset stop` command stops a running preset creation and its runs.

##### Usage

<div class="termy">

```shell
$ dstack preset stop --help
#GENERATE#
```

</div>

## dstack preset get

The `dstack preset get` command outputs one locally stored preset as JSON.

##### Usage

<div class="termy">

```shell
$ dstack preset get --help
#GENERATE#
```

</div>

## dstack preset resume

The `dstack preset resume` command resumes an interrupted preset creation.

##### Usage

<div class="termy">

```shell
$ dstack preset resume --help
#GENERATE#
```

</div>

## dstack preset export

The `dstack preset export` command exports a preset as a service
configuration that `dstack apply` deploys.

##### Usage

<div class="termy">

```shell
$ dstack preset export --help
#GENERATE#
```

</div>

## dstack preset push

The `dstack preset push` command pushes a local preset to the registry as
`<project>/<name>`.

##### Usage

<div class="termy">

```shell
$ dstack preset push --help
#GENERATE#
```

</div>

## dstack preset pull

The `dstack preset pull` command pulls `<project>/<name>` or `<project>/<id>`
from the registry and stores it locally.

##### Usage

<div class="termy">

```shell
$ dstack preset pull --help
#GENERATE#
```

</div>

## dstack preset delete

The `dstack preset delete` command deletes one local preset by ID or name, or
all presets for a base model.

##### Usage

<div class="termy">

```shell
$ dstack preset delete --help
#GENERATE#
```

</div>
