from urllib.parse import quote

# shim (runs on the host) HTTP API port
DSTACK_SHIM_HTTP_PORT = 10998
# runner (runs inside a container) HTTP API port
DSTACK_RUNNER_HTTP_PORT = 10999
# ssh server (runs alongside the runner inside a container) listen port
DSTACK_RUNNER_SSH_PORT = 10022
# Private socket created inside jobs that request access to the dstack server.
DSTACK_RUN_SERVER_SOCKET_PATH = "/run/dstack/server.sock"
DSTACK_RUN_SERVER_URL = f"http+unix://{quote(DSTACK_RUN_SERVER_SOCKET_PATH, safe='')}"
DSTACK_PROJECT_ENV = "DSTACK_PROJECT"
DSTACK_SERVER_URL_ENV = "DSTACK_SERVER_URL"
DSTACK_TOKEN_ENV = "DSTACK_TOKEN"
# legacy AWS, Azure, GCP, and OCI image for older GPUs
DSTACK_OS_IMAGE_WITH_PROPRIETARY_NVIDIA_KERNEL_MODULES = "0.10"
