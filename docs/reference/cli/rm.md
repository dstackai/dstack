# dstack rm

Use this command to remove finished runs within the current Git repo.

## Usage

<div class="termy">

```shell
$ dstack rm --help
Usage: dstack rm [-h] [-a] [-y] [RUN]

Positional Arguments:
  RUN         A name of a run

Optional Arguments:
  -a, --all   Remove all finished runs
  -y, --yes   Don't ask for confirmation
```

</div>

## Arguments reference

One of the following arguments is required:

- `RUN` - A name of a particular run
-  `-a`, `--all` – Remove all finished runs 

The following arguments are optional:

-  `-y`, `--yes` – (Optional) Don't ask for confirmation 
