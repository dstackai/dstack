# dstack run

This command runs a given workflow or a provider.

[//]: # (!!! info "NOTE:")

[//]: # (    Make sure to use the CLI from within a Git repo directory.)

[//]: # (    When you run a workflow, dstack detects the current branch, commit hash, and local changes.)

## Usage

<div class="termy">

```shell
$ dstack run --help
Usage: dstack run [-h] [--remote] [-t TAG] [-d] [WORKFLOW | PROVIDER] [ARGS ...]

Positional Arguments:
  WORKFLOW | PROVIDER   A workflow or provider name
  ARGS                  Override workflow or provider arguments
  
  
Optional Arguments:
  --remote              Run it remotely
  -t, --tag TAG         A tag name. Warning, if the tag exists, it will be overridden.
  -d, --detach          Do not poll for status update and logs
```

</div>

## Arguments reference

The following arguments are required:

- `WORKFLOW | PROVIDER` - (Required) A name of a workflow or provider

The following arguments are optional:

- `-t TAG`, `--tag TAG` – (Optional) A tag name. Warning, if the tag exists, it will be overridden.
- `-r`, `--remote` – (Optional) Run it remotely.
- `-d`, `--detach` – (Optional) Run the workflow in the detached mode. Means, the `run` command doesn't
  poll for logs and workflow status, but exits immediately.
- `ARGS` – (Optional) Use `ARGS` to pass [workflow arguments](../../usage/args.md) or override provider arguments
- `-h`, `--help` – (Optional) Shows help for the `dstack run` command. Combine it with the name of a workflow
  or provider to see the provider-specific help message.

!!! info "NOTE:"
By default, it runs it in the attached mode, so you'll see the output in real-time as your
workflow is running.