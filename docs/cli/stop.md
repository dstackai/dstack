# stop

The `stop` command stops runs within the current Git repository.

### Usage

```shell
dstack stop [-x] [-y] (RUN | -a)
```

#### Arguments reference

One of the following arguments is required:

- `RUN` - A name of a particular run
-  `-a`, `--all` – Stop all unfinished runs 

The following arguments are optional:

-  `-x`, `--abort` – (Optional) Don't wait for a graceful stop and abort the run immediately 
-  `-y`, `--yes` – (Optional) Don't ask for confirmation 
