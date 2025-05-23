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

- STEP 1: The user submits the run. `services.runs.submit_run` creates jobs with status `SUBMITTED`. Now the run has status `SUBMITTED`.
- STEP 2: `background.tasks.process_runs` periodically pulls unfinished runs and processes them:
	- If any job is `RUNNING`, the run becomes `RUNNING`.
	- If any job is `PROVISIONING` or `PULLING`, the run becomes `PROVISIONING`.
	- If any job fails and cannot be retried, the run becomes `TERMINATING`, and after processing, `FAILED`.
	- If all jobs are `DONE`, the run becomes `TERMINATING`, and after processing, `DONE`.
	- If any job fails, can be retried, and there is any other active job, the failed job will be resubmitted in-place.
	- If any jobs in a replica fail and can be retried and there is other active replicas, the jobs of the failed replica are resubmitted in-place (without stopping other replicas). But if some jobs in a replica fail, then all the jobs in a replica are terminated and resubmitted. This include multi-node tasks that represent one replica with multiple jobs.
	- If all jobs fail and can be resubmitted, the run becomes `PENDING`.
- STEP 3: If the run is `TERMINATING`, the server makes all jobs `TERMINATING`. `background.tasks.process_runs` sets their status to `TERMINATING`, assigns `JobTerminationReason`, and sends a graceful stop command to `dstack-runner`. `process_terminating_jobs` then ensures that jobs are terminated assigns a finished status.
- STEP 4: Once all jobs are finished, the run becomes `TERMINATED`, `DONE`, or `FAILED` based on `RunTerminationReason`.
- STEP 0: If the run is `PENDING`, `background.tasks.process_runs` will resubmit jobs. The run becomes `SUBMITTED` again.

> No one must assign the finished status to the run, except `services.runs.process_terminating_run`. To terminate the run, assign `TERMINATING` status and `RunTerminationReason`.

### Services

Services' lifecycle has some modifications:

- During STEP 1, the service is registered on the gateway. If the gateway is not accessible or the domain name is taken, the run submission fails.
- During STEP 2, downscaled jobs are ignored.
- During STEP 4, the service is unregistered on the gateway.
- During STEP 0, the service can stay in `PENDING` status if it was downscaled to zero (WIP).

### When can the job be retried?

`dstack` retries the run only if:

- The configuration enables `retry`.
- The job termination reason is covered by `retry.on_events`.
- The `retry.duration` is not exceeded.

## Job's Lifecycle

- STEP 1: A newly submitted job has status `SUBMITTED`. It is not assigned to any instance yet.
- STEP 2: `background.tasks.process_submitted_jobs` tries to assign an existing instance or provision a new one.
	- On success, the job becomes `PROVISIONING`.
	- On failure, the job becomes `TERMINATING`, and after processing, `FAILED` because of `FAILED_TO_START_DUE_TO_NO_CAPACITY`.
- STEP 3: `background.tasks.process_running_jobs` periodically pulls unfinished jobs and processes them.
	- While `dstack-shim`/`dstack-runner` is not responding, the job stays `PROVISIONING`.
	- Once `dstack-shim` (for VM-featured backends) becomes available, it submits the docker image name, and the job becomes `PULLING`.
	- Once `dstack-runner` inside a docker container becomes available, it submits the code and the job spec, and the job becomes `RUNNING`.
	- If `dstack-shim` or `dstack-runner` don't respond for a long time or fail to respond after successful connection and multiple retries, the job becomes `TERMINATING`, and after processing, `FAILED`.
- STEP 4: `background.tasks.process_running_jobs` processes `RUNNING` jobs, pulling job logs, runner logs, and job status.
	- If the pulled status is `DONE`, the job becomes `TERMINATING`, and after processing, `DONE`.
	- Otherwise, the job becomes `TERMINATING`, and after processing, `FAILED`.
- STEP 5: `background.tasks.process_terminating_jobs` processes `TERMINATING` jobs.
	- If the job has `remove_at` in the future, nothing happens. This is to give the job some time for a graceful stop.
	- Once `remove_at` is in the past, it stops the container via `dstack-shim`, detaches instance volumes, and releases the instance. The job becomes `TERMINATED`, `DONE`, `FAILED`, or `ABORTED` based on `JobTerminationReason`.
	- If some volumes fail to detach, it keeps the job `TERMINATING` and checks volumes attachment status.

> No one must assign the finished status to the job, except `services.jobs.process_terminating_job`. To terminate the job, assign `TERMINATING` status and `JobTerminationReason`.

### Services' Jobs

Services' jobs lifecycle has some modifications:

- During STEP 3, once the job becomes `RUNNING`, it is registered on the gateway as a replica. If the gateway is not accessible, the job fails.
- During STEP 5, the job is unregistered on the gateway (WIP).
