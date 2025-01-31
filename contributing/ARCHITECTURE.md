# Architecture

## Overview

The `dstack` platform consists of six major components:

* Server
* Python API
* CLI
* Runner
* Shim
* Gateway (optional)

The server provides an HTTP API for submitting runs and managing all of the `dstack` functionality including users, projects, backends, repos, secrets, and gateways.

The Python API consists of the low-level and high-level Python API. The low-level Python API is a Python wrapper around the server's HTTP API. It's available as `dstack.api.server`. The high-level API provides a more convenient interface to work with `dstack` programmatically. It's available as `dstack.api`. The `dstack` CLI is implemented on top of the high-level API.

When the server provisions a cloud instance for a run, it launches a Docker image with the runner inside the image. The runner provides an HTTP API that the server uses for submitting the run, uploading the code, fetching logs and so on.

The shim may be or may not be present depending on which type of cloud is used. If it's a GPU cloud that provides an API for running Docker images, then no shim is required. If it's a traditional cloud that provisions VMs, then the shim is started on the VM launch. It pulls and runs the Docker image, controls its execution, and implements any cloud-specific functionality such as terminating the instance.

The gateway makes jobs available via a public URL. It works like a reverse proxy that forwards requests to the job instance via an SSH tunnel.

## Implementation of `dstack apply`

When a user applies a run configuration with `dstack apply`, the CLI sends the run configuration and other profile parameters to the server to get the run plan. The server iterates over configured backends to get all instance offers matching the requirements
and their availability. If the user is willing to proceed with the offers suggested, the CLI uploads the code from the user's machine to the server and submits the run configuration.

Note: If a git repository is used, `dstack` only uploads the code diff. The runner then pulls the repository and applies the diff to get the copy of the user's files. The `dstack init` command uploads git credentials to the server so that the runner can access private repositories.

The submitted runs are stored in the server database. For each run, the server also creates one or more jobs. (Multiple jobs allow for distributed runs and multi-replica services.) For each job, it creates a job submission. If a job submission fails, the server may create new submissions.

A background worker fetches a job submission and iterates over configured backends to provision an instance. It tries best offers first until the provisioning succeeds. The instance is instructed to run the shim on the launch. In case of "Docker-only" clouds, the docker image is run directly.

A successfully provisioned job enters the provisioning state. Another background worker processes such jobs. It waits for the runner to become available and submits the job.

Note: The runner HTTP API is not exposed publicly. In order to use it, the server established an SSH connection to the instance. The runner HTTP API becomes available via port-forwarding.

After the job is submitted, the job enters the running state. A background worker pings the runner periodically for the job status and logs updates.

When all job's commands are executed, the runner marks job as done, the container exists, and the shim terminates the instance. The job may also be interrupted by `dstack stop` that asks the runner shutdown gracefully. The `--abort` flag tells the server to force instance shutdown without notifying the runner and waiting for the runner graceful stop.

## Project structure

The server is a FastAPI app backend by SQLite or Postgres. The runner and shim are written in Go.

* `docker/` – Dockefiles for `dstack` images
* `docs/` – source files for mkdocs generated documentation
* `runner/` – source code for the runner and the shim
* `scripts/` – dev/CI/CD scripts and packer files for building `dstack` cloud VM images.
* `src/` – source code for the `dstack` Python package that includes the server, the CLI and the Python API
    * `dstack/`
        * `_internal/` – modules hidden from the users of the `dstack` Python API
            * `cli/` – CLI source code
            * `core/` – core `dstack` business logic that is not API, CLI or server specific. Although most of it is used only on the server side as of now (e.g. backends).
                * `backends/` – core backends logic (e.g. compute provisioning, pricing, etc)
                * `models/` – core `dstack` pydantic models. For simplicity, server-specific models also live here. Put the model here if unsure.
                    * `backends/` – backend-specific models such as configs used by the server
                * `services/` – other business logic implemented on top of `models/`
            * `server/` – server source code
                * `background/` – server background workers
                * `migrations/` – alembic migrations
                * `routers/` – API endpoints implementation, a thin wrapper around `services/`.
                * `schemas/` – request/response-specific pydantic models. Other server models live in `dstack._internal.core.models`.
                * `security/` – permissions 
                * `services/` – core server business logic
                    * `backends/`
                        * `configurators/` – backend configurators responsible for configuring and creating backends from API configs
                    * `jobs/`
                        * `configurators/` – job configurators responsible for making `JobSpec` from `RunSpec`
                * `utils/` – server-specific utils
                * `alembic.ini`
                * `db.py` – db class and utils
                * `main.py` – server entrypoint
                * `models.py` – sqlalchemy models
                * `settings.py` – server global settings
            * `utils/` – utils common for all modules
        * `api/` – public Python API
            * `_public` – the implementation of the high-level Python API
            * `server` – the low-level Python API (a Python wrapper around server's HTTP API)
        * `core/` – core Python API modules (e.g. `dstack` errors)
    * `tests/`
* `gateway/src/dstack/gateway` - source code for the gateway application
  * `openai/` - OpenAI API proxy
  * `registry/` - gateway services registry
  * `systemd/` - systemd service files
