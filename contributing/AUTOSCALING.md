# Autoscaling

`dstack` features auto-scaling for services published via the gateway. The general flow is:

- STEP 1: `dstack-gateway` parses nginx `access.log` to collect per-second statistics about requests to the service and request times.
- STEP 2: `dstack-gateway` aggregates statistics over a 1-minute window.
- STEP 3: The dstack server pulls all service statistics in the `process_gateways` background task.
- STEP 4: The `process_runs` background task passes statistics and current replicas to the autoscaler.
- STEP 5: The autoscaler (configured via the `dstack.yml` file) returns the replica change as an int.
- STEP 6: `process_runs` calls `scale_run_replicas` to add or remove replicas.
- STEP 7: `scale_run_replicas` terminates or starts replicas.
    - `SUBMITTED` and `PROVISIONING` replicas get terminated before `RUNNING`.
    - Replicas are terminated by descending `replica_num` and launched by ascending `replica_num`.

## RPSAutoscaler

`RPSAutoscaler` implements simple target tracking scaling. The target value represents requests per second per replica (in a 1-minute window).

`scale_up_delay` tells how much time has to pass since the last upscale or downscale event before the next upscaling. `scale_down_delay` tells how much time has to pass since the last upscale or downscale event before the next downscaling.
