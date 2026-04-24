# Runs and jobs

## Introduction

Run is the primary unit of workload in `dstack`. Users can:

1. Submit a run using `dstack apply` or the API.
2. Stop a run using `dstack stop` or the API.

Runs are created from run configurations. There are three types of run configurations:

1. `dev-environment` — runs a VS Code server.
2. `task` — runs the user's bash script until completion.
3. `service` — runs the user's bash script and exposes a port through [dstack-proxy](PROXY.md).

A run can spawn one or multiple jobs, depending on the configuration. A task that specifies multiple `nodes` spawns a job for every node (a multi-node task). A service that specifies multiple `replicas` spawns a job for every replica. A job submission is always assigned to one particular instance. If a job fails and the configuration allows retrying, the server creates a new job submission for the job.

## Run's Lifecycle

- STEP 1: The user submits the run. `services.runs.submit_run` creates jobs with status `SUBMITTED`. The run starts in `SUBMITTED`.
- STEP 2: `RunPipeline` continuously processes unfinished runs.
  - For active runs, it derives the run status from the latest job states in priority order:
    1. If any non-retryable failure is present, the run becomes `TERMINATING` with the relevant `RunTerminationReason`.
    2. If `stop_criteria == MASTER_DONE` and the master job is done, the run becomes `TERMINATING` with `ALL_JOBS_DONE`.
    3. Otherwise, if any job is `RUNNING`, the run becomes `RUNNING`.
    4. Otherwise, if any job is `PROVISIONING` or `PULLING`, the run becomes `PROVISIONING`.
    5. Otherwise, if jobs are still waiting for placement or provisioning, the run stays `SUBMITTED`.
    6. Otherwise, if all contributing jobs are `DONE`, the run becomes `TERMINATING` with `ALL_JOBS_DONE`.
    7. Otherwise, if no active replicas remain and the run should be retried, the run becomes `PENDING`.
  - Retryable replica failures are handled before the final transition is applied:
    - If a replica fails with a retryable reason while other replicas are still active, `RunPipeline` creates a new `SUBMITTED` submission for that replica and terminates the old jobs in that replica.
    - If all remaining work is retryable, the run ends up in `PENDING`.
- STEP 3: If the run is `PENDING`, `RunPipeline` processes it in the pending phase.
  - For retrying runs, it waits for an exponential backoff before resubmitting.
  - For scheduled runs, it waits until `next_triggered_at`.
  - For scaled-to-zero services, it can keep the run in `PENDING` until autoscaling wants replicas again.
  - Once the run is ready to continue, `RunPipeline` creates new `SUBMITTED` jobs and moves the run back to `SUBMITTED`.
- STEP 4: If the run is `TERMINATING`, `RunPipeline` marks active jobs as `TERMINATING` and assigns the corresponding `JobTerminationReason`.
- STEP 5: Once all jobs are finished, the terminating phase of `RunPipeline` either:
  - assigns the final run status (`TERMINATED`, `DONE`, or `FAILED`), or
  - for scheduled runs that were not stopped or aborted by the user, returns the run to `PENDING` and computes a new `next_triggered_at`.

### Services

Services' run lifecycle has some modifications:

- During STEP 1, the service itself is registered on the gateway or the in-server proxy. If the gateway is not accessible or the domain name is taken, submission fails.
- During STEP 2, active run processing also computes desired replica counts from gateway stats and handles scale-up, scale-down, rolling deployment, and cleanup of removed replica groups.
- During STEP 2, jobs already marked `SCALED_DOWN` do not contribute to the run status.
- During STEP 3, a service can stay in `PENDING` when autoscaling currently wants zero replicas.
- During STEP 5, the terminating phase of `RunPipeline` unregisters the service from the gateway.

### When can the job be retried?

`dstack` retries the run only if:

- The configuration enables `retry`.
- The job termination reason is covered by `retry.on_events`.
- The `retry.duration` is not exceeded.

## Job's Lifecycle

- STEP 1: A newly submitted job has status `SUBMITTED`. It is not assigned to any instance yet.
- STEP 2: `JobSubmittedPipeline` assigns the job in two phases:
  - Assignment: claim an existing instance or reserve a *placeholder* `InstanceModel`. Placeholders are `PENDING` instances that reserve an `instance_num` and a `nodes.max` slot. `InstancePipeline` ignores them.
  - Provisioning: reuse the existing instance, or cloud-provision and promote the placeholder to `PROVISIONING`.
  - On success, the job becomes `PROVISIONING`.
  - On failure, the job becomes `TERMINATING`. `JobTerminatingPipeline` later assigns the final failed status.
- STEP 3: `JobRunningPipeline` processes `PROVISIONING`, `PULLING`, and `RUNNING` jobs.
  - While `dstack-shim` / `dstack-runner` is not responding, the job stays `PROVISIONING`.
  - Once `dstack-shim` (for VM-featured backends) becomes available, the pipeline submits the image and the job becomes `PULLING`.
  - Once `dstack-runner` inside the container becomes available, the pipeline uploads the code and job spec, and the job becomes `RUNNING`.
  - While the job is `RUNNING`, the pipeline keeps collecting logs and runner status.
  - If startup, runner communication, or replica registration fails, the job becomes `TERMINATING`.
- STEP 4: Once the job is actually ready, `JobRunningPipeline` initializes probes.
- STEP 5: `JobTerminatingPipeline` processes `TERMINATING` jobs.
  - If the job has `remove_at` in the future, it waits. This gives the job time for a graceful stop.
  - Once `remove_at` is in the past, it stops the container, detaches volumes, unregisters service replicas if needed, and releases the instance assignment.
  - If some volumes are not detached yet, the job stays `TERMINATING` and is retried.
  - When cleanup is complete, the job becomes `TERMINATED`, `DONE`, `FAILED`, or `ABORTED` based on `JobTerminationReason`.

### Services' Jobs

Services' jobs lifecycle has some modifications:

- During STEP 3, once the primary job of a replica is `RUNNING` and ready to receive traffic, `JobRunningPipeline` registers that replica on the gateway. If the gateway is not accessible, the job fails with a gateway-related termination reason.
- During STEP 5, `JobTerminatingPipeline` unregisters the replica from receiving requests before the job is fully cleaned up.
