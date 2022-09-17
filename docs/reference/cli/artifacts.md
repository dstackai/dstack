# artifacts

The `artifacts` command allows to access artifacts of runs and tags within the current Git repository.

It supports the following subcommands: `list`, and `download`.

## artifacts list

The `artifacts list` command lists the files of the artifacts of a given run or tag.

### Usage

```shell
dstack artifacts list (RUN | :TAG)
```

### Arguments reference

One of the following arguments is required:

- `RUN` - A name of a run
- `TAG` - A name of a tag

## artifacts download

The `artifacts download` command downloads the files of the artifacts of a given run or tag.

### Usage

```shell
dstack artifacts download [-o OUTPUT] (RUN | :TAG)
```

### Arguments reference

One of the following arguments is required:

- `RUN` - A name of a run
- `TAG` - A name of a tag

The following arguments are optional:

- `-o`, `--output` – (Optional) The directory to download artifacts to. By default, it's the current directory.