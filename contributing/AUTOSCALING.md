# Autoscaling

`dstack` features auto-scaling for services published via the gateway. The general flow is:

- STEP 1: `dstack-gateway` parses nginx `access.log` to collect per-second statistics about requests to the service and request times.
- STEP 2: `dstack-gateway` aggregates statistics over a 1-minute window.
- STEP 3: The server keeps gateway connections alive in the scheduled `process_gateways_connections` task and continuously collects stats from active gateways. This is separate from `GatewayPipeline`, which handles gateway provisioning and deletion.
- STEP 4: When `RunPipeline` processes a service run, it loads the latest collected gateway stats for that service.
- STEP 5: The autoscaler (configured via `dstack.yml`) computes the desired replica count for each replica group.
- STEP 6: `RunPipeline` applies that desired state.
    - For scale-up, it creates new `SUBMITTED` jobs. `JobSubmittedPipeline` then assigns existing capacity or provisions new capacity for them.
    - For scale-down, it marks the least-important active replicas as `TERMINATING` with `SCALED_DOWN`. `JobTerminatingPipeline` unregisters and cleans them up.
- STEP 7: If the service is in rolling deployment, `RunPipeline` handles that in the same active-run processing path.
    - It allows only a limited surge of replacement replicas.
    - It delays teardown of old replicas until replacement capacity is available.
    - It also cleans up replicas that belong to replica groups removed from the configuration.

## RPSAutoscaler

`RPSAutoscaler` implements simple target tracking scaling. The target value represents requests per second per replica (in a 1-minute window).

`scale_up_delay` tells how much time has to pass since the last upscale or downscale event before the next upscaling. `scale_down_delay` tells how much time has to pass since the last upscale or downscale event before the next downscaling.
