# dstack logs

Use this command to see logs of a given run within the current Git repo.

### Usage

```shell
dstack logs [-a] [-s SINCE] RUN
```

#### Arguments reference

The following arguments are required:

- `RUN` - (Required) A name of a run

The following arguments are optional:

-  `-a`, `--attach` – (Optional) Whether to continuously poll for new logs while the workflow is still running. 
   By default, the command will exit once there are no more logs to display. To exit from this mode, use `Ctrl+C`.
- `-s SINCE`, `--since SINCE` – (Optional) From what time to begin displaying logs. By default, logs will be displayed
  starting from 24 hours in the past. The value provided can be an ISO 8601 timestamp or a
  relative time. For example, a value of `5m` would indicate to display logs starting five
  minutes in the past.
