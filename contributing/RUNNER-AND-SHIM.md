# runner and shim

`dstack` runs the user's configuration as a Docker container. The user can specify their own image name or use the preconfigured dstack image (with Python and CUDA).

`dstack-runner` is a component responsible for setting environment variables and secrets, executing user commands, reporting logs and job status, and terminating the job on signal from the `dstack` server. `dstack-runner` is cloud-agnostic and runs as an entrypoint of a Docker container.

If the cloud provider has VM capabilities, `dstack` runs `dstack-shim` on the host to emulate a container-only environment. `dstack-shim` is responsible for pulling Docker images (public or private), configuring Docker containers (mounts, GPU forwarding, entrypoint, etc.), running Docker containers, and terminating the container on signal from the `dstack` server.

## dstack-shim

`dstack-shim` works in cycles, allowing to run a different container once the job is finished.

- STEP 1: Wait for Docker image info (+ registry auth credentials if needed) from the dstack server
- STEP 2: Pull the Docker image
- STEP 3: Run the container
	- Wait for container exit
	- Or wait for the interruption signal from the dstack server
- STEP 4: Go to STEP 1

All communication between the `dstack` server and `dstack-shim` happens via REST API through an SSH tunnel. `dstack-shim` doesn't collect logs. Usually, it is run from a `cloud-init` user-data script.
The entrypoint for the container:
- Installs `openssh-server`
- Adds project and user public keys to `~/.ssh/authorized_keys`
- Downloads `dstack-runner` from the public S3 bucket
- Starts `dstack-runner`

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

`dstack-shim` must also be running next to the SSH server. The `dstack` server connects to this SSH server for interacting with both `dstack-shim` and `dstack-runner` since we use `host` networking mode for the Docker container. The CLI uses this SSH server as a jump host because the user wants to connect to the container.

> `host` networking mode would allow jobs to use any port at any moment for internal communication. For example, during distributed PyTorch training.