# dstack logs

This command shows the output of a given run within the current repository.

## Usage

<div class="termy">

```shell
$ dstack logs --help
Usage: dstack logs [-h] [--project PROJECT] [-a] [-s SINCE] RUN

Positional Arguments:
  RUN                   The name of the run

Optional Arguments:
  --project PROJECT     The name of the Hub project to execute the command for
  -d, --diagnose        Show diagnostic logs
  -s, --since SINCE     From what time to begin displaying logs. By default, logs will be
                        displayed starting from 24 hours in the past. The value provided can be an
                        ISO 8601 timestamp or a relative time. For example, a value of 5m would
                        indicate to display logs starting five minutes in the past.
```

</div>

## Arguments reference

The following arguments are required:

- `RUN` - (Required) The name of the run

The following arguments are optional:

- `--project PROJECT` - (Optional) The name of the Hub project to execute the command for
- `-d`, `--diagnose` - (Optional) Show diagnostic logs
- `-s SINCE`, `--since SINCE` – (Optional) From what time to begin displaying logs. By default, logs will be displayed
  starting from 24 hours in the past. The value provided can be an ISO 8601 timestamp or a
  relative time. For example, a value of `5m` would indicate to display logs starting five
  minutes in the past.