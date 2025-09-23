# shim (runs on the host) HTTP API port
DSTACK_SHIM_HTTP_PORT = 10998
# runner (runs inside a container) HTTP API port
DSTACK_RUNNER_HTTP_PORT = 10999
# ssh server (runs alongside the runner inside a container) listen port
DSTACK_RUNNER_SSH_PORT = 10022
# legacy AWS, Azure, GCP, and OCI image for older GPUs
DSTACK_OS_IMAGE_WITH_PROPRIETARY_NVIDIA_KERNEL_MODULES = "0.10"
