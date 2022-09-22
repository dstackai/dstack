# dstack ps

Use this command to show status of runs within the current Git repo.

### Usage

```shell
dstack ps [-a | RUN]
```

#### Arguments reference

The following arguments are optional and mutually exclusive:

-  `-a`, `--all` – (Optional) Show status of all runs
- `RUN` - (Optional) A name of a run

!!! info "NOTE:"
    If no arguments are specified, the command shows status of unfinished runs if any or otherwise the 
    last finished run.