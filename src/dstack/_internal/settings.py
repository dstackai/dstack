import os

from dstack import version
from dstack._internal.utils.version import parse_version

DSTACK_VERSION = os.getenv("DSTACK_VERSION", version.__version__)
if parse_version(DSTACK_VERSION) is None:
    # The build backend (hatching) requires not None for versions,
    # but the code currently treats None as dev version.
    # TODO: update the code to treat 0.0.0 as dev version.
    DSTACK_VERSION = None
DSTACK_RELEASE = os.getenv("DSTACK_RELEASE") is not None or version.__is_release__
DSTACK_RUNNER_VERSION = os.getenv("DSTACK_RUNNER_VERSION")
DSTACK_RUNNER_VERSION_URL = os.getenv("DSTACK_RUNNER_VERSION_URL")
DSTACK_RUNNER_DOWNLOAD_URL = os.getenv("DSTACK_RUNNER_DOWNLOAD_URL")
DSTACK_RUNNER_ALLOW_DOWNGRADE = os.getenv("DSTACK_RUNNER_ALLOW_DOWNGRADE") is not None
DSTACK_SHIM_VERSION = os.getenv("DSTACK_SHIM_VERSION")
DSTACK_SHIM_VERSION_URL = os.getenv("DSTACK_SHIM_VERSION_URL")
DSTACK_SHIM_DOWNLOAD_URL = os.getenv("DSTACK_SHIM_DOWNLOAD_URL")
DSTACK_SHIM_ALLOW_DOWNGRADE = os.getenv("DSTACK_SHIM_ALLOW_DOWNGRADE") is not None
DSTACK_USE_LATEST_FROM_BRANCH = os.getenv("DSTACK_USE_LATEST_FROM_BRANCH") is not None
DSTACK_GATEWAY_PACKAGE_URL = os.getenv("DSTACK_GATEWAY_PACKAGE_URL")


DSTACK_DOCKER_BASE_IMAGE = os.getenv("DSTACK_DOCKER_BASE_IMAGE", "dstackai/base")
DSTACK_DOCKER_BASE_IMAGE_VERSION = os.getenv(
    "DSTACK_DOCKER_BASE_IMAGE_VERSION", version.docker_base_image
)
DSTACK_DOCKER_BASE_IMAGE_UBUNTU_VERSION = os.getenv(
    "DSTACK_DOCKER_BASE_IMAGE_UBUNTU_VERSION", version.docker_base_image_ubuntu_version
)
DSTACK_VM_BASE_IMAGE_VERSION = os.getenv("DSTACK_VM_BASE_IMAGE_VERSION", version.vm_base_image)
DSTACK_VM_BASE_IMAGE_PREFIX = os.getenv("DSTACK_VM_BASE_IMAGE_PREFIX", "")  # e.g. stgn-123-
DSTACK_DIND_IMAGE = os.getenv("DSTACK_DIND_IMAGE", "dstackai/dind")

CLI_LOG_LEVEL = os.getenv("DSTACK_CLI_LOG_LEVEL", "INFO").upper()
CLI_FILE_LOG_LEVEL = os.getenv("DSTACK_CLI_FILE_LOG_LEVEL", "DEBUG").upper()


class FeatureFlags:
    """
    dstack feature flags. Feature flags are temporary and can be used when developing
    large features. This class may be empty if there are no such features in
    development. Feature flags are environment variables of the form DSTACK_FF_*
    """

    CLI_PRINT_JOB_CONNECTION_INFO = (
        os.getenv("DSTACK_FF_CLI_PRINT_JOB_CONNECTION_INFO") is not None
    )
    """If DSTACK_FF_CLI_PRINT_JOB_CONNECTION_INFO enabled, `dstack apply` command prints server-provided
    IDE URL(s) and SSH command(s) before job logs (for dev-environments only).
    """

    # TODO: Drop once offers carry the minimum reservation period and `dstack` keeps such instances
    # idle until it ends.
    HOTAISLE_BARE_METAL_NO_FORCE_RELEASE = (
        os.getenv("DSTACK_FF_HOTAISLE_BARE_METAL_NO_FORCE_RELEASE", "1") != "0"
    )
    """Enabled unless set to `0`. If enabled, Hot Aisle bare metal servers are deleted without `force`,
    so a server still within its minimum reservation period isn't deleted and must be released
    manually. This prevents accidentally losing a prepaid server.
    """
