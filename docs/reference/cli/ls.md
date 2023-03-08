# dstack ls

The `ls` command lists the files of the artifacts of a given run or tag.

## Usage

```shell
dstack ls [-r] [-t] (RUN | :TAG) [SEARCH_PREFIX]
```

### Arguments reference

One of the following arguments is required:

- `RUN` – A name of a run
- `:TAG` – A name of a tag

The following arguments are optional:

- `-r`, `--recursive` – (Optional) Show all files recursively
- `-t`, `--total` – (Optional) Show total folder size
- `SEARCH_PREFIX` – (Optional) Show files starting with prefix