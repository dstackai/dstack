# dstack tags

## dstack tags list

The `tags list` command lists tags.

### Usage

<div class="termy">

```shell
$ dstack tags list
```

</div>

## dstack tags add

The `tags add` command creates a new tag. A tag and its artifacts can be later added as a dependency in a workflow.

There are two ways of creating a tag:

1. Tag a finished run 
2. Upload local data

### Usage

<div class="termy">

```shell
$ dstack tags add --help
Usage: dstack tags add [-h] [-a PATH] [-y] TAG [RUN]

Positional Arguments:
  TAG                   The name of the tag
  RUN                   The name of the run

Options:
  -a, --artifact PATH   A path to local directory to upload as an artifact
  -y, --yes             Don't ask for confirmation
```

</div>

### Arguments reference

The following argument is required:

- `TAG` – (Required) The name of the tag.

One of the following arguments is also required:

- `RUN` – (Optional) The name of the run
- `-a PATH`, `--artifact PATH` - (Optional) The path to the local folder to be uploaded as an artifact.

### Examples:

Tag the finished run `wet-mangust-1` with the `some_tag_1` tag:

<div class="termy">

```shell
$ dstack tags add some_tag_1 wet-mangust-1
```

</div>

Uploading two local folders `./output1` and `./output2` to create the `some_tag_2` tag:

<div class="termy">

```shell
$ dstack tags add some_tag_2 -a ./output1 -a ./output2
```

</div>

!!! info "NOTE:"
    To list or download the artifacts of a tag, use the `dstack artifacts list :TAG` and 
    `dstack artifacts download :TAG` commands.

## dstack tags delete

The `tags delete` command deletes a given tag.

### Usage

<div class="termy">

```shell
$ dstack tags delete --help
Usage: dstack tags delete [-h] [-y] TAG_NAME

Positional Arguments:
  TAG_NAME    The name of the tag

Optional Arguments:
  -y, --yes   Don't ask for confirmation
```

</div>

### Arguments reference

The following arguments are required:

- `TAG` - (Required) The name of the tag

The following arguments are optional:

-  `-y`, `--yes` – (Optional) Don't ask for confirmation 