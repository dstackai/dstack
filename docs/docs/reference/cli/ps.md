# dstack ps

This command shows status of runs within the current repository.

## Usage

<div class="termy">

```shell
$ dstack ps --help
Usage: dstack ps [-h] [--project PROJECT] [-a] [-v] [-w] [RUN]

Positional Arguments:
  RUN                The name of the run

Options:
  --project PROJECT  The name of the Hub project to execute the command for
  -a, --all          Show all runs. By default, it only shows unfinished runs or the last finished.
  -v, --verbose      Show more information about runs
  -w, --watch        Watch statuses of runs in realtime
```

</div>

## Arguments reference

The following arguments are optional and mutually exclusive:

-  `-a`, `--all` – (Optional) Show all runs
- `RUN` - (Optional) The name of the run

!!! info "NOTE:"
    If `-a` is not used, the command shows only the statuses of active runs and the last finished one.

The following arguments are optional:

-  `--project PROJECT` – (Optional) The name of the Hub project to execute the command for
- `-v`, `--verbose` – (Optional) Show more information about runs
- `-w`, `--watch` - (Optional) Watch statuses of runs in realtime
