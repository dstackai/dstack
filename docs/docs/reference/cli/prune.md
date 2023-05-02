# dstack prune cache

The `prune` command prunes the cache of a specific workflow.

## Usage

<div class="termy">

```shell
$ dstack prune cache --help

Usage: dstack prune cache [-h] [--project PROJECT] WORKFLOW

Positional Arguments:
  WORKFLOW    A workflow name to prune cache
  
Optional Arguments:
  --project PROJECT  The name of the Hub project to execute the command for
```

</div>

### Arguments reference

The following arguments are required:

- `--project PROJECT` - (Optional) The name of the Hub project to execute the command for
- `WORKFLOW` — (Required) A workflow name to prune cache
