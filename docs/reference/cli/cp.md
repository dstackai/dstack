# dstack cp

The `cp` command copies artifact files to a local target path.

## Usage

```shell
dstack cp (RUN | :TAG) SOURCE TARGET
```

### Arguments reference

One of the following arguments is required:

- `RUN` – A name of a run
- `:TAG` – A name of a tag

The following arguments are required:

- `SOURCE` – A path of an artifact file or directory
- `TARGET` – A local path to download artifact file or directory into
