# dstack tags

## dstack tags list

The `tags list` command lists tags.

### Usage

```shell
dstack tags list
```

## dstack tags add

The `tags add` command creates a new tag. A tag and its artifacts can be later added as a dependency in a workflow.

There are two ways of creating a tag:

1. Tag a finished run 
2. Upload local data

### Usage

```shell
dstack tags add TAG (-r RUN | -a PATH ...)
```

### Arguments reference

The following argument is required:

- `TAG` – (Required) A name of the tag. Must be unique within the current Git repo.

One of the following arguments is also required:

- `-r`, `--run` - A name of a run
- `-a PATH`, `--artifact PATH` - A path to a local folder to be uploaded as an artifact.

### Examples:

Tag the finished run `wet-mangust-1` with the `some_tag_1` tag:

```shell
dstack tags add some_tag_1 wet-mangust-1
```

Uploading two local folders `./output1` and `./output2` to create the `some_tag_2` tag:

```shell
dstack tags add some_tag_2 -a ./output1 -a ./output2
```

!!! info "NOTE:"
    To list or download the artifacts of a tag, use the `dstack artifacts list :TAG` and 
    `dstack artifacts download :TAG` commands.

## dstack tags delete

The `tags delete` command deletes a given tag.

### Usage

```shell
dstack tags delete [-y] TAG
```

### Arguments reference

The following arguments are required:

- `TAG` - (Required) A name of a tag

The following arguments are optional:

-  `-y`, `--yes` – (Optional) Don't ask for confirmation 