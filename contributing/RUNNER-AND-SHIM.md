# runner and shim

`dstack` runs the user's configuration as a Docker container. The user can specify their own image name or use the preconfigured dstack image (with Python and CUDA).

`dstack-runner` is a component responsible for setting environment variables and secrets, executing user commands, reporting logs and job status, and terminating the job on signal from the `dstack` server. `dstack-runner` is cloud-agnostic and runs as an entrypoint of a Docker container.

If the cloud provider has VM capabilities, `dstack` runs `dstack-shim` on the host to emulate a container-only environment. `dstack-shim` is responsible for pulling Docker images (public or private), configuring Docker containers (mounts, GPU forwarding, entrypoint, etc.), running Docker containers, and terminating the container on signal from the `dstack` server.

## dstack-shim

`dstack-shim` works with _tasks_. Essentially, a task is a `dstack-shim`-specific part of `dstack`'s job, namely a Docker container with its associated data. `dstack-shim` is able to process multiple tasks in parallel.

A task is identified by a unique ID assigned by the `dstack` server. A task has a state: a status, allocated resources, data on disk (container, even if stopped, runner logs), etc. `dstack-shim` keeps a task in memory and its data on disk until the `dstack` server requests removal. The `dstack` server should periodically remove old tasks to clean up storage. Currently, the server removes a task right after termination request, but this is subject to change.

A lifecycle of a task is as follows:

- Wait for a task submission from the `dstack` server (image ref, registry credentials if needed, user, resource constraints, network mode, etc.)
- Allocate GPU resources, find and mount volumes, pull the image
- Run the container and
  - either wait for container to exit
  - or wait for the termination request from the `dstack` server
- Deallocate GPU resources, unmount volumes

A container is started in either `host` or `bridge` network mode depending on the instance and the job:

- If the instance is shared (split into GPU blocks), network mode is set to `bridge` to avoid port conflicts
- …unless there are multiple jobs in multinode mode — in that case, the instance is never shared (the jobs takes the whole instance), and network mode is set `host`

  **NOTE**: `host` networking mode would allow jobs to use any port at any moment for internal communication. For example, during distributed PyTorch training.
- If the instance is not shared by multiple jobs (i.e. GPU blocks feature is not used), network mode is `host` to avoid unnecessary overhead

In `bridge` mode, container ports are mapped to ephemeral host ports. `dstack-shim` stores port mapping as a part of task's state. Currently, the default `bridge` network is used for all containers, but this could be changed in the future to improve container isolation.

All communication between the `dstack` server and `dstack-shim` happens via REST API through an SSH tunnel. `dstack-shim` doesn't collect logs. Usually, it is run from a `cloud-init` user-data script.

The entrypoint for the container:
- Installs `openssh-server`
- Adds project and user public keys to `~/.ssh/authorized_keys`
- Starts `sshd` and `dstack-runner`

## dstack-runner

`dstack-runner` has a linear lifecycle:

- STEP 1: Wait for the job spec submission
- STEP 2: Wait for the code (tarball or diff)
- STEP 3: Prepare the repo (clone git repo and apply the diff, or extract the archive)
- STEP 4: Run the commands from the job spec
  - Wait for the commands to exit
  - Serve logs to the `dstack` server via HTTP
  - Serve real-time logs to the CLI via WebSocket
  - Wait for the signal to terminate the commands
- STEP 5: Wait until all logs are read by the server and the CLI. Or exit after a timeout

All communication between the `dstack` server and `dstack-runner` happens via REST API through an SSH tunnel. `dstack-runner` collects the job logs and its own logs. Only the job logs are served via WebSocket.

## SSH tunnels

`dstack` expects a running SSH server right next to the `dstack-runner`. It provides a secure channel for communication with the runner API and forwarding any ports without listening for `0.0.0.0`. The `dstack-gateway` also uses this SSH server for forwarding requests from public endpoints.

`dstack-shim` must also be running next to the SSH server. The `dstack` server connects to this SSH server for interacting with both `dstack-shim` and `dstack-runner`. The CLI uses this SSH server as a jump host because the user wants to connect to the container.
