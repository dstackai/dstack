# dstack stop

This command stops run(s) within the current repository.

## Usage

<div class="termy">

```shell
$ dstack stop --help
Usage: dstack stop [-h] [--project PROJECT] [-a] [-x] [-y] [RUN]

Positional Arguments:
  RUN                The name of the run

Optional Arguments:
  --project PROJECT  The name of the Hub project to execute the command for
  -a, --all          Stop all unfinished runs
  -x, --abort        Don't wait for a graceful stop and abort the run immediately
  -y, --yes          Don't ask for confirmation
```

</div>

### Arguments reference

One of the following arguments is required:

- `RUN` - The name of a particular run
-  `-a`, `--all` – Stop all unfinished runs 

The following arguments are optional:

- `--project PROJECT` - (Optional) The name of the Hub project to execute the command for
-  `-x`, `--abort` – (Optional) Don't wait for a graceful stop and abort the run immediately 
-  `-y`, `--yes` – (Optional) Don't ask for confirmation 