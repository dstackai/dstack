# dstack cp

The `cp` command copies artifact files to a local target path.

## Usage

<div class="termy">

```shell
$ dstack cp --help
Usage: dstack cp [-h] (RUN | :TAG) SOURCE TARGET

Positional Arguments:
  (RUN | :TAG)  A name of a run or a tag
  SOURCE        A path of an artifact file or directory
  TARGET        A local path to download artifact file or directory into
```

</div>

### Arguments reference

One of the following arguments is required:

- `RUN` – A name of a run
- `:TAG` – A name of a tag

The following arguments are required:

- `SOURCE` – A path of an artifact file or directory
- `TARGET` – A local path to download artifact file or directory into
