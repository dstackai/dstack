# dstack ps

This command shows status of runs within the current Git repo.

## Usage

<div class="termy">

```shell
$ dstack ps --help
Usage: dstack ps [-h] [-a] [-w] [RUN]

Positional Arguments:
  RUN          A name of a run

Optional Arguments:
  -a, --all       Show all runs. By default, it only shows unfinished runs or the last finished.
  -v, --verbose   Show more information about runs
  -w, --watch     Watch statuses of runs in realtime
```

</div>

## Arguments reference

The following arguments are optional and mutually exclusive:

-  `-a`, `--all` – (Optional) Show all runs
- `RUN` - (Optional) A name of a run

!!! info "NOTE:"
    If `-a` is not used, the command shows only the statuses of active runs and the last finished one.

The following arguments are optional:

- `-v`, `--verbose` – (Optional) Show more information about runs
- `-w`, `--watch` - (Optional) Watch statuses of runs in realtime
