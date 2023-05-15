# dstack cp

The `cp` command copies artifact files to a local target path.

## Usage

<div class="termy">

```shell
$ dstack cp --help
Usage: dstack cp [-h] (RUN | :TAG) SOURCE TARGET

Positional Arguments:
  (RUN | :TAG)  The name of the run or the tag
  SOURCE        A path of an artifact file or directory
  TARGET        A local path to download artifact file or directory into
```

</div>

### Arguments reference

One of the following arguments is required:

- `RUN` – The name of the run
- `:TAG` – The name of the tag

The following arguments are required:

- `SOURCE` – A path of an artifact file or directory
- `TARGET` – A local path to download artifact file or directory into
