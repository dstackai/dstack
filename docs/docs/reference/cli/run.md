# dstack run

This command runs a given workflow or a provider.

## Usage

<div class="termy">

```shell
$ dstack run --help
Usage: dstack run [-h] [--project PROJECT] [-t TAG] [-d] [WORKFLOW | PROVIDER] [ARGS ...]

Positional Arguments:
  WORKFLOW | PROVIDER  A name of a workflow or a provider
  ARGS                 Override workflow or provider arguments

Options:
  --project PROJECT    The name of the Hub project to execute the command for
  -t, --tag TAG        A tag name. Warning, if the tag exists, it will be overridden.
  -d, --detach         Do not poll for status update and logs
```

</div>

## Arguments reference

The following arguments are required:

- `WORKFLOW | PROVIDER` - (Required) A name of a workflow or provider

The following arguments are optional:

- `--project PROJECT` – (Optional) The name of the Hub project to execute the command for
- `-t TAG`, `--tag TAG` – (Optional) A tag name. Warning, if the tag exists, it will be overridden.
- `-d`, `--detach` – (Optional) Run the workflow in the detached mode. Means, the `run` command doesn't
  poll for logs and workflow status, but exits immediately.
- `ARGS` – (Optional) Use `ARGS` to pass [workflow arguments](../../usage/args.md) or override provider arguments
- `-h`, `--help` – (Optional) Shows help for the `dstack run` command. Combine it with the name of a workflow
  or provider to see the provider-specific help message.

!!! info "NOTE:"
  By default, it runs it in the attached mode, so you'll see the output in real-time as your
  workflow is running.