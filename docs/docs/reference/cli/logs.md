# dstack logs

This command shows the output of a given run within the current repository.

## Usage

<div class="termy">

```shell
$ dstack logs --help
#GENERATE#
```

</div>

## Arguments reference

The following arguments are required:

- `RUN` - (Required) The name of the run

The following arguments are optional:

- `--project PROJECT` - (Optional) The name of the project to execute the command for
- `-d`, `--diagnose` - (Optional) Show diagnostic logs
- `-s SINCE`, `--since SINCE` – (Optional) From what time to begin displaying logs. By default, logs will be displayed
  starting from 24 hours in the past. The value provided can be an ISO 8601 timestamp or a
  relative time. For example, a value of `5m` would indicate to display logs starting five
  minutes in the past.