# dstack pull

The `pull` command downloads the artifacts of a given run or tag from the configured remote (e.g. 
to the configured cloud account) to the local cache (`~/.dstack/artifacts`).

## Usage

<div class="termy">

```shell
$ dstack pull --help
Usage: dstack pull [-h] (RUN | :TAG)

Positional Arguments:
  (RUN | :TAG)  A name of a run or a tag
```

</div>

## Arguments reference

One of the following arguments is required:

- `RUN` - A name of a run
- `:TAG` - A name of a tag