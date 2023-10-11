# dstack stop

This command stops run(s) within the current repository.

## Usage

<div class="termy">

```shell
$ dstack stop --help
#GENERATE#
```

</div>

### Arguments reference

One of the following arguments is required:

- `RUN` - The name of a particular run
-  `-a`, `--all` – Stop all unfinished runs 

The following arguments are optional:

- `--project PROJECT` - (Optional) The name of the project to execute the command for
-  `-x`, `--abort` – (Optional) Don't wait for a graceful stop and abort the run immediately 
-  `-y`, `--yes` – (Optional) Don't ask for confirmation 