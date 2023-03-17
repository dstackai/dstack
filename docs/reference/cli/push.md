# dstack push

The `push` command pushes the artifacts of a local run to the configured remote (e.g. 
to the configured cloud account).

## Usage

<div class="termy">

```shell
$ dstack push --help
Usage: dstack push [-h] (RUN | :TAG)

Positional Arguments:
  (RUN | :TAG)  A name of a run or a tag
```

</div>

## Arguments reference

One of the following arguments is required:

- `RUN` - A name of a run
- `:TAG` - A name of a tag