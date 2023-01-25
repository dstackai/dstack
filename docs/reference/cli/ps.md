# dstack ps

This command shows status of runs within the current Git repo.

## Usage

```shell
dstack ps [-a | RUN]
```

### Arguments reference

The following arguments are optional and mutually exclusive:

-  `-a`, `--all` – (Optional) Show status of all runs
- `RUN` - (Optional) A name of a run

!!! info "NOTE:"
    If `-a` is not used, the command shows only the status of active runs, the last finished one.