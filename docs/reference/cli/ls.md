# dstack ls

The `ls` command lists the files of the artifacts of a given run or tag.

## Usage

<div class="termy">

```shell
$ dstack ls --help
Usage: dstack ls [-h] [-r] [-t] RUN | :TAG [SEARCH_PREFIX]

Positional Arguments:
  RUN | :TAG       A name of a run or a tag
  SEARCH_PREFIX    Show files starting with prefix

Optional Arguments:
  -r, --recursive  Show all files recursively
  -t, --total      Show total folder size
```

</div>

### Arguments reference

One of the following arguments is required:

- `RUN` – A name of a run
- `:TAG` – A name of a tag

The following arguments are optional:

- `-r`, `--recursive` – (Optional) Show all files recursively
- `-t`, `--total` – (Optional) Show total folder size
- `SEARCH_PREFIX` – (Optional) Show files starting with prefix