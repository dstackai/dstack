## Introduction

Run is a primary unit of workload in dstack. User can:
1. Submit a run using `dstack run` or API
2. Stop a run using `dstack stop` or API

Runs are created from configurations. There are three basic types of configurations:
1. `dev-environment` — runs VS Code server
2. `task` — runs user's bash script until the completion
3. `service` — runs user's bash script and expose a port through gateway, making it accessible from the internet via HTTP protocol

A run can spawn one or multiple jobs, it depends on a configuration. There could be multiple nodes in a cluster (for distributed training), multiple replicas (for load balancing) or both. During the execution a job is running on an instance, the instance can run only one job at any given moment.

If a job fails and the configuration allows retrying, the server will spawn a new job submission for the job.

## Run's lifecycle

- STEP 1: user submits the run. `services.runs.submit_run` creates jobs with status `SUBMITTED`. Now the run has status `SUBMITTED`
- STEP 2: the server periodically pulls not finished runs and process them in `background.tasks.process_runs`
	- If any job is `RUNNING` — the run becomes `RUNNING`
	- If any job is `PROVISIONING` or `PULLING` — the run becomes `STARTING`
	- If any job fails and cannot be retried — the run becomes `TERMINATING`, and after the processing, `FAILED`
	- If all jobs are `DONE` — the run becomes `TERMINATING`, and after the processing, `DONE`
	- If any job fails, can be retried and there is any other active job — failed job will be resubmitted in-place. The run status is defined by the rules above
	- If all jobs fail and can be resubmitted — the run becomes `PENDING`
- STEP 3: if the run is `TERMINATING`, the server terminates all jobs by setting their status to `TERMINATING` and assigning proper `JobTerminationReason`
- STEP 4: once all jobs are finished, the run becomes `TERMINATED`, `DONE`, or `FAILED` based on `RunTerminationReason`
- STEP 0: if the run is `PENDING`, `background.tasks.process_runs` will resubmit jobs. The run becomes `SUBMITTED` again

> No one must assign finished status to the run, except of `services.runs.process_terminating_run`. To terminate the run assign `TERMINATING` status and `RunTerminationReason`

### Services
Services lifecycle has some modifications:
- During STEP 1, the service is registered on the gateway. If the gateway is not accessible or domain name is taken, the run submission fails
- During STEP 2, down scaled jobs are ignored
- During STEP 4, the service is unregistered on the gateway
- During STEP 0, the service can stay in `PENDING` status, if it was down scaled to zero (WIP)

### When does the job can be retried?
It's a complicated question and would be elaborated later with multi-node and replicas implementation.

As for now, dstack retries only if:
- The configuration has enabled retry policy
- The job failed because of `NO_CAPACITY` and the instance was a spot

## Job's lifecycle

- STEP 1: newly submitted job has status `SUBMITTED`. It is not assigned to any instance yet
- STEP 2: `background.tasks.process_submitted_jobs` tries to assign an existing instance or provision a new one
	- On success, the job becomes `PROVISIONING`
	- On failure, the job becomes `TERMINATING`, and after the processing, `FAILED` because of `NO_CAPACITY`
- STEP 3: `background.tasks.process_running_jobs` periodically pulls not finished jobs and process them
	- While `dstack-shim`/`dstack-runner` is not responding — the job stays `PROVISIOINING`
	- Once `dstack-shim` (for vm-featured backends) becomes available, the server submits docker image name — the job becomes `PULLING`
	- Once `dstack-runner` inside of a docker container becomes available, the server submits the code and the job spec — the job becomes `RUNNING`
	- If `dstack-shim` or `dstack-runner` don't respond for a long time, or fail to respond after successful connection and multiple retries — the job becomes `TERMINATING`, and after the processing, `FAILED`
- STEP 4: `background.tasks.process_running_jobs` processes `RUNNING` jobs, pulling job logs, runner logs, and job status
	- If pulled status is `DONE` — the job becomes `TERMINATING`, and after the processing, `DONE`
	- Otherwise — the job becomes `TERMINATING`, and after the processing, `FAILED`
- STEP 5: `background.tasks.process_terminating_jobs` processes `TERMINATING` jobs
	- If the job has `remove_at` in the future — nothing happens
	- Once `remove_at` is in the past, the server stops the container via `dstack-shim` and releases the instance — the job becomes `TERMINATED`, `DONE`, `FAILED`, or `ABORTED` based on `JobTerminationReason`

> No one must assign finished status to the job, except of `services.jobs.process_terminating_job`. To terminate the job assign `TERMINATING` status and `JobTerminationReason`

### Services' jobs
Services' jobs lifecycle has some modifications:
- During STEP 3, once the job becomes `RUNNING`, it is registered on the gateway as a replica. If the gateway is not accessible, the job fails
- During STEP 5, the job is unregistered on the gateway (WIP)

## Stop a run
To stop a run, `services.runs.stop_runs` assigns `TERMINATING` status to the run and executes one iteration of the processing without waiting for the background task.