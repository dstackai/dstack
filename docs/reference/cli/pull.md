# dstack pull

The `pull` command downloads the artifacts of a given run or tag from the configured remote (e.g. 
to the configured cloud account) to the local cache (`~/.dstack/artifacts`).

## Usage

```shell
dstack pull (RUN | :TAG)
```

### Arguments reference

One of the following arguments is required:

- `RUN` - A name of a run
- `:TAG` - A name of a tag