# dstack ps

This command shows status of runs within the current repository.

## Usage

<div class="termy">

```shell
$ dstack ps --help
#GENERATE#
```

</div>

## Arguments reference

The following arguments are optional and mutually exclusive:

-  `-a`, `--all` – (Optional) Show all runs
- `RUN` - (Optional) The name of the run

!!! info "NOTE:"
    If `-a` is not used, the command shows only the statuses of active runs and the last finished one.

The following arguments are optional:

-  `--project PROJECT` – (Optional) The name of the project to execute the command for
- `-v`, `--verbose` – (Optional) Show more information about runs
- `-w`, `--watch` - (Optional) Watch statuses of runs in realtime
