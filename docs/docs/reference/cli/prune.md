# dstack prune cache

The `prune` command prunes the cache of a specific configuration.

## Usage

<div class="termy">

```shell
$ dstack prune cache --help

Usage: dstack prune cache [-h] [--project PROJECT] [-f FILE] WORKING_DIR

Positional Arguments:
  WORKING_DIR           The working directory of the run

Optional Arguments:
  --project PROJECT     The name of the project
  -f, --file FILE       The path to the run configuration file. Defaults to
                        WORKING_DIR/.dstack.yml.
```

</div>

### Arguments reference

The following arguments are required:

- `WORKING_DIR` - (Required) The working directory of the run (e.g. `.`)

The following arguments are optional:

- `-f FILE`, `--f FILE` – (Optional) The path to the run configuration file. Defaults to `WORKING_DIR/.dstack.yml`.
- `--project PROJECT` - (Optional) The name of the Hub project to execute the command for
