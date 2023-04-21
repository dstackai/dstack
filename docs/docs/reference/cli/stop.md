# dstack stop

This command stops run(s) within the current Git repo.

## Usage

<div class="termy">

```shell
$ dstack stop --help
Usage: dstack stop [-h] [-a] [-x] [-y] [RUN]

Positional Arguments:
  RUN          A name of a run

Optional Arguments:
  -a, --all    Stop all unfinished runs
  -x, --abort  Don't wait for a graceful stop and abort the run immediately
  -y, --yes    Don't ask for confirmation
```

</div>

### Arguments reference

One of the following arguments is required:

- `RUN` - A name of a particular run
-  `-a`, `--all` – Stop all unfinished runs 

The following arguments are optional:

-  `-x`, `--abort` – (Optional) Don't wait for a graceful stop and abort the run immediately 
-  `-y`, `--yes` – (Optional) Don't ask for confirmation 