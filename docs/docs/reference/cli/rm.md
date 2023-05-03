# dstack rm

Use this command to remove finished runs within the current repository.

## Usage

<div class="termy">

```shell
$ dstack rm --help
Usage: dstack rm [-h] [--project PROJECT] [-a] [-y] [RUN]

Positional Arguments:
  RUN                The name of the run

Optional Arguments:
  --project PROJECT  The name of the Hub project to execute the command for
  -a, --all          Remove all finished runs
  -y, --yes          Don't ask for confirmation
```

</div>

## Arguments reference

One of the following arguments is required:

- `RUN` - The name of a particular run
-  `-a`, `--all` – Remove all finished runs 

The following arguments are optional:

- `--project PROJECT` - (Optional) The name of the Hub project to execute the command for
- `-y`, `--yes` – (Optional) Don't ask for confirmation 
