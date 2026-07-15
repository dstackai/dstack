# dstack endpoint

The `dstack endpoint` commands create, list, apply, and delete local
[endpoint presets](../../../concepts/endpoints.md).

## dstack endpoint preset list

The `dstack endpoint preset list` command lists locally stored presets.

##### Usage

<div class="termy">

```shell
$ dstack endpoint preset list --help
#GENERATE#
```

</div>

## dstack endpoint preset create

The `dstack endpoint preset create` command uses an agent to create and save a
verified preset from an endpoint configuration.

##### Usage

<div class="termy">

```shell
$ dstack endpoint preset create --help
#GENERATE#
```

</div>

##### Agent settings

Set either `DSTACK_AGENT_ANTHROPIC_API_KEY` or
`DSTACK_AGENT_CLAUDE_USE_EXISTING_AUTH` before creating a preset.

| Variable | Description |
| --- | --- |
| `DSTACK_AGENT_ANTHROPIC_API_KEY` | Anthropic API key used by the agent. |
| `DSTACK_AGENT_CLAUDE_USE_EXISTING_AUTH` | Use the existing `claude` login. |
| `DSTACK_AGENT_CLAUDE_PATH` | `claude` executable name or path. Defaults to `claude` from `PATH`. |
| `DSTACK_AGENT_ANTHROPIC_MODEL` | Claude model used by the agent. Defaults to `claude-opus-4-8`. |
| `DSTACK_AGENT_CLAUDE_EFFORT` | Claude effort level: `low`, `medium`, `high`, `xhigh`, or `max`. If unset, the `claude` CLI default is used. |

Agent progress is written to `agent.log` under
`~/.dstack/agent/<endpoint-name>/<timestamp>-<preset-id>/`. Failed attempts use
the `-failed` suffix. Pass `--debug` to also save the effective endpoint
configuration (`endpoint.dstack.yml`), agent prompt (`prompt.md`), and raw trace
(`trace.jsonl`).

## dstack endpoint preset get

The `dstack endpoint preset get` command outputs one locally stored preset as JSON.

##### Usage

<div class="termy">

```shell
$ dstack endpoint preset get --help
#GENERATE#
```

</div>

## dstack endpoint preset apply

The `dstack endpoint preset apply` command selects a matching local preset and
submits its service.

##### Usage

<div class="termy">

```shell
$ dstack endpoint preset apply --help
#GENERATE#
```

</div>

## dstack endpoint preset delete

The `dstack endpoint preset delete` command deletes one local preset by ID or
all presets for a base model.

##### Usage

<div class="termy">

```shell
$ dstack endpoint preset delete --help
#GENERATE#
```

</div>
