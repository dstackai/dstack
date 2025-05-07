import os
import random
import re
import string
import threading
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Literal, Optional

import git
import requests
import yaml
from cachetools import TTLCache, cachedmethod

from dstack._internal import settings
from dstack._internal.core.consts import (
    DSTACK_RUNNER_HTTP_PORT,
    DSTACK_RUNNER_SSH_PORT,
    DSTACK_SHIM_HTTP_PORT,
)
from dstack._internal.core.models.gateways import (
    GatewayComputeConfiguration,
    GatewayProvisioningData,
)
from dstack._internal.core.models.instances import (
    InstanceConfiguration,
    InstanceOffer,
    InstanceOfferWithAvailability,
    SSHKey,
)
from dstack._internal.core.models.placement import PlacementGroup, PlacementGroupProvisioningData
from dstack._internal.core.models.runs import Job, JobProvisioningData, Requirements, Run
from dstack._internal.core.models.volumes import (
    Volume,
    VolumeAttachmentData,
    VolumeProvisioningData,
)
from dstack._internal.core.services import is_valid_dstack_resource_name
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.path import PathLike

logger = get_logger(__name__)

DSTACK_SHIM_BINARY_NAME = "dstack-shim"
DSTACK_RUNNER_BINARY_NAME = "dstack-runner"

GoArchType = Literal["amd64", "arm64"]


class Compute(ABC):
    """
    A base class for all compute implementations with minimal features.
    If a compute supports additional features, it must also subclass `ComputeWith*` classes.
    """

    def __init__(self):
        self._offers_cache_lock = threading.Lock()
        self._offers_cache = TTLCache(maxsize=5, ttl=30)

    @abstractmethod
    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        """
        Returns offers with availability matching `requirements`.
        If the provider is added to gpuhunt, typically gets offers using `base.offers.get_catalog_offers()`
        and extends them with availability info.
        """
        pass

    @abstractmethod
    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
        volumes: List[Volume],
    ) -> JobProvisioningData:
        """
        Launches a new instance for the job. It should return `JobProvisioningData` ASAP.
        If required to wait to get the IP address or SSH port, return partially filled `JobProvisioningData`
        and implement `update_provisioning_data()`.
        """
        pass

    @abstractmethod
    def terminate_instance(
        self,
        instance_id: str,
        region: str,
        backend_data: Optional[str] = None,
    ) -> None:
        """
        Terminates an instance by `instance_id`.
        If the instance does not exist, it should not raise errors but return silently.

        Should return ASAP. If required to wait for some operation, raise `NotYetTerminated`.
        In this case, the method will be called again after a few seconds.
        """
        pass

    def update_provisioning_data(
        self,
        provisioning_data: JobProvisioningData,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ):
        """
        This method is called if `JobProvisioningData` returned from `run_job()`/`create_instance()`
        is not complete, e.g. missing `hostname` or `ssh_port`.
        It can be used if getting complete provisioning data takes a long of time.
        It should not wait but return immediately.
        If it raises `ProvisioningError`, there will be no further attempts to update the provisioning data,
        and the run will be terminated.
        """
        pass

    def _get_offers_cached_key(self, requirements: Optional[Requirements] = None) -> int:
        # Requirements is not hashable, so we use a hack to get arguments hash
        if requirements is None:
            return hash(None)
        return hash(requirements.json())

    @cachedmethod(
        cache=lambda self: self._offers_cache,
        key=_get_offers_cached_key,
        lock=lambda self: self._offers_cache_lock,
    )
    def get_offers_cached(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        return self.get_offers(requirements)


class ComputeWithCreateInstanceSupport(ABC):
    """
    Must be subclassed and implemented to support fleets (instance creation without running a job).
    Typically, a compute that runs VMs would implement it,
    and a compute that runs containers would not.
    """

    @abstractmethod
    def create_instance(
        self,
        instance_offer: InstanceOfferWithAvailability,
        instance_config: InstanceConfiguration,
        placement_group: Optional[PlacementGroup],
    ) -> JobProvisioningData:
        """
        Launches a new instance. It should return `JobProvisioningData` ASAP.
        If required to wait to get the IP address or SSH port, return partially filled `JobProvisioningData`
        and implement `update_provisioning_data()`.
        """
        pass

    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
        volumes: List[Volume],
    ) -> JobProvisioningData:
        """
        The default `run_job()` implementation for all backends that support `create_instance()`.
        Override only if custom `run_job()` behavior is required.
        """
        instance_config = InstanceConfiguration(
            project_name=run.project_name,
            instance_name=get_job_instance_name(run, job),
            user=run.user,
            ssh_keys=[SSHKey(public=project_ssh_public_key.strip())],
            volumes=volumes,
            reservation=run.run_spec.configuration.reservation,
            tags=run.run_spec.merged_profile.tags,
        )
        instance_offer = instance_offer.copy()
        self._restrict_instance_offer_az_to_volumes_az(instance_offer, volumes)
        return self.create_instance(instance_offer, instance_config, placement_group=None)

    def _restrict_instance_offer_az_to_volumes_az(
        self,
        instance_offer: InstanceOfferWithAvailability,
        volumes: List[Volume],
    ):
        if len(volumes) == 0:
            return
        volume = volumes[0]
        if (
            volume.provisioning_data is not None
            and volume.provisioning_data.availability_zone is not None
        ):
            if instance_offer.availability_zones is None:
                instance_offer.availability_zones = [volume.provisioning_data.availability_zone]
            instance_offer.availability_zones = [
                z
                for z in instance_offer.availability_zones
                if z == volume.provisioning_data.availability_zone
            ]


class ComputeWithMultinodeSupport:
    """
    Must be subclassed to support multinode tasks and cluster fleets.
    Instances provisioned in the same project/region must be interconnected.
    """

    pass


class ComputeWithReservationSupport:
    """
    Must be subclassed to support provisioning from reservations.
    """

    pass


class ComputeWithPlacementGroupSupport(ABC):
    """
    Must be subclassed and implemented to support placement groups.
    """

    @abstractmethod
    def create_placement_group(
        self,
        placement_group: PlacementGroup,
        master_instance_offer: InstanceOffer,
    ) -> PlacementGroupProvisioningData:
        """
        Creates a placement group.

        Args:
            placement_group: details about the placement group to be created
            master_instance_offer: the first instance dstack will attempt to add
                                   to the placement group
        """
        pass

    @abstractmethod
    def delete_placement_group(
        self,
        placement_group: PlacementGroup,
    ):
        """
        Deletes a placement group.
        If the group does not exist, it should not raise errors but return silently.
        """
        pass

    @abstractmethod
    def is_suitable_placement_group(
        self,
        placement_group: PlacementGroup,
        instance_offer: InstanceOffer,
    ) -> bool:
        """
        Checks if the instance offer can be provisioned in the placement group.

        Should return immediately, without performing API calls.

        Can be called with an offer originating from a different backend, because some backends
        (BackendType.DSTACK) produce offers on behalf of other backends. Should return `False`
        in that case.
        """
        pass


class ComputeWithGatewaySupport(ABC):
    """
    Must be subclassed and implemented to support gateways.
    """

    @abstractmethod
    def create_gateway(
        self,
        configuration: GatewayComputeConfiguration,
    ) -> GatewayProvisioningData:
        """
        Creates a gateway instance.
        """
        pass

    @abstractmethod
    def terminate_gateway(
        self,
        instance_id: str,
        configuration: GatewayComputeConfiguration,
        backend_data: Optional[str] = None,
    ):
        """
        Terminates a gateway instance. Generally, it passes the call to `terminate_instance()`,
        but may perform additional work such as deleting a load balancer when a gateway has one.
        """
        pass


class ComputeWithPrivateGatewaySupport:
    """
    Must be subclassed to support private gateways.
    `create_gateway()` must be able to create private gateways.
    """

    pass


class ComputeWithVolumeSupport(ABC):
    """
    Must be subclassed and implemented to support volumes.
    """

    @abstractmethod
    def register_volume(self, volume: Volume) -> VolumeProvisioningData:
        """
        Returns VolumeProvisioningData for an existing volume.
        Used to add external volumes to dstack.
        """
        pass

    @abstractmethod
    def create_volume(self, volume: Volume) -> VolumeProvisioningData:
        """
        Creates a new volume.
        """
        raise NotImplementedError()

    @abstractmethod
    def delete_volume(self, volume: Volume):
        """
        Deletes a volume.
        """
        raise NotImplementedError()

    def attach_volume(self, volume: Volume, instance_id: str) -> VolumeAttachmentData:
        """
        Attaches a volume to the instance.
        If the volume is not found, it should raise `ComputeError()`.
        Implement only if compute may return `VolumeProvisioningData.attachable`.
        Otherwise, volumes should be attached by `run_job()`.
        """
        raise NotImplementedError()

    def detach_volume(self, volume: Volume, instance_id: str, force: bool = False):
        """
        Detaches a volume from the instance.
        Implement only if compute may return `VolumeProvisioningData.detachable`.
        Otherwise, volumes should be detached on instance termination.
        """
        raise NotImplementedError()

    def is_volume_detached(self, volume: Volume, instance_id: str) -> bool:
        """
        Checks if a volume was detached from the instance.
        If `detach_volume()` may fail to detach volume,
        this method should be overridden to check the volume status.
        The caller will trigger force detach if the volume gets stuck detaching.
        """
        return True


def get_dstack_working_dir(base_path: Optional[PathLike] = None) -> str:
    if base_path is None:
        base_path = "/root"
    return str(Path(base_path, ".dstack"))


def get_dstack_shim_binary_path(bin_path: Optional[PathLike] = None) -> str:
    if bin_path is None:
        bin_path = "/usr/local/bin"
    return str(Path(bin_path, DSTACK_SHIM_BINARY_NAME))


def get_dstack_runner_binary_path(bin_path: Optional[PathLike] = None) -> str:
    if bin_path is None:
        bin_path = "/usr/local/bin"
    return str(Path(bin_path, DSTACK_RUNNER_BINARY_NAME))


def get_job_instance_name(run: Run, job: Job) -> str:
    return job.job_spec.job_name


_DEFAULT_MAX_RESOURCE_NAME_LEN = 60
_CLOUD_RESOURCE_SUFFIX_LEN = 8


def generate_unique_instance_name(
    instance_configuration: InstanceConfiguration,
    max_length: int = _DEFAULT_MAX_RESOURCE_NAME_LEN,
) -> str:
    """
    Generates a unique instance name valid across all backends.
    """
    return generate_unique_backend_name(
        resource_name=instance_configuration.instance_name,
        project_name=instance_configuration.project_name,
        max_length=max_length,
    )


def generate_unique_instance_name_for_job(
    run: Run,
    job: Job,
    max_length: int = _DEFAULT_MAX_RESOURCE_NAME_LEN,
) -> str:
    """
    Generates a unique instance name for a job valid across all backends.
    """
    return generate_unique_backend_name(
        resource_name=get_job_instance_name(run, job),
        project_name=run.project_name,
        max_length=max_length,
    )


def generate_unique_gateway_instance_name(
    gateway_compute_configuration: GatewayComputeConfiguration,
    max_length: int = _DEFAULT_MAX_RESOURCE_NAME_LEN,
) -> str:
    """
    Generates a unique gateway instance name valid across all backends.
    """
    return generate_unique_backend_name(
        resource_name=gateway_compute_configuration.instance_name,
        project_name=gateway_compute_configuration.project_name,
        max_length=max_length,
    )


def generate_unique_volume_name(
    volume: Volume,
    max_length: int = _DEFAULT_MAX_RESOURCE_NAME_LEN,
) -> str:
    """
    Generates a unique volume name valid across all backends.
    """
    return generate_unique_backend_name(
        resource_name=volume.name,
        project_name=volume.project_name,
        max_length=max_length,
    )


def generate_unique_placement_group_name(
    project_name: str,
    fleet_name: str,
    max_length: int = _DEFAULT_MAX_RESOURCE_NAME_LEN,
) -> str:
    """
    Generates a unique placement group name valid across all backends.
    """
    return generate_unique_backend_name(
        resource_name=fleet_name,
        project_name=project_name,
        max_length=max_length,
    )


def generate_unique_backend_name(
    resource_name: str,
    project_name: Optional[str],
    max_length: int,
) -> str:
    """
    Generates a unique resource name valid across all backends.
    Backend resource names must be unique on every provisioning so that
    resource re-submission/re-creation doesn't lead to conflicts
    on backends that require unique names (e.g. Azure, GCP).
    """
    # resource_name is guaranteed to be valid in all backends
    prefix = f"dstack-{resource_name}"
    if project_name is not None and is_valid_dstack_resource_name(project_name):
        # project_name is not guaranteed to be valid in all backends,
        # so we add it only if it passes the validation
        prefix = f"dstack-{project_name}-{resource_name}"
    return _generate_unique_backend_name_with_prefix(
        prefix=prefix,
        max_length=max_length,
    )


def _generate_unique_backend_name_with_prefix(
    prefix: str,
    max_length: int,
) -> str:
    prefix_len = max_length - _CLOUD_RESOURCE_SUFFIX_LEN - 1
    prefix = prefix[:prefix_len]
    suffix = "".join(
        random.choice(string.ascii_lowercase + string.digits)
        for _ in range(_CLOUD_RESOURCE_SUFFIX_LEN)
    )
    return f"{prefix}-{suffix}"


def get_cloud_config(**config) -> str:
    return "#cloud-config\n" + yaml.dump(config, default_flow_style=False)


def get_user_data(
    authorized_keys: List[str],
    backend_specific_commands: Optional[List[str]] = None,
    base_path: Optional[PathLike] = None,
    bin_path: Optional[PathLike] = None,
    backend_shim_env: Optional[Dict[str, str]] = None,
) -> str:
    shim_commands = get_shim_commands(
        authorized_keys=authorized_keys,
        base_path=base_path,
        bin_path=bin_path,
        backend_shim_env=backend_shim_env,
    )
    commands = (backend_specific_commands or []) + shim_commands
    return get_cloud_config(
        runcmd=[["sh", "-c", " && ".join(commands)]],
        ssh_authorized_keys=authorized_keys,
    )


def get_shim_env(
    authorized_keys: List[str],
    base_path: Optional[PathLike] = None,
    bin_path: Optional[PathLike] = None,
    backend_shim_env: Optional[Dict[str, str]] = None,
    arch: Optional[str] = None,
) -> Dict[str, str]:
    log_level = "6"  # Trace
    envs = {
        "DSTACK_SHIM_HOME": get_dstack_working_dir(base_path),
        "DSTACK_SHIM_HTTP_PORT": str(DSTACK_SHIM_HTTP_PORT),
        "DSTACK_SHIM_LOG_LEVEL": log_level,
        "DSTACK_RUNNER_DOWNLOAD_URL": get_dstack_runner_download_url(arch),
        "DSTACK_RUNNER_BINARY_PATH": get_dstack_runner_binary_path(bin_path),
        "DSTACK_RUNNER_HTTP_PORT": str(DSTACK_RUNNER_HTTP_PORT),
        "DSTACK_RUNNER_SSH_PORT": str(DSTACK_RUNNER_SSH_PORT),
        "DSTACK_RUNNER_LOG_LEVEL": log_level,
        "DSTACK_PUBLIC_SSH_KEY": "\n".join(authorized_keys),
    }
    if backend_shim_env is not None:
        envs |= backend_shim_env
    return envs


def get_shim_commands(
    authorized_keys: List[str],
    *,
    is_privileged: bool = False,
    pjrt_device: Optional[str] = None,
    base_path: Optional[PathLike] = None,
    bin_path: Optional[PathLike] = None,
    backend_shim_env: Optional[Dict[str, str]] = None,
    arch: Optional[str] = None,
) -> List[str]:
    commands = get_shim_pre_start_commands(
        base_path=base_path,
        bin_path=bin_path,
        arch=arch,
    )
    shim_env = get_shim_env(
        authorized_keys=authorized_keys,
        base_path=base_path,
        bin_path=bin_path,
        backend_shim_env=backend_shim_env,
        arch=arch,
    )
    for k, v in shim_env.items():
        commands += [f'export "{k}={v}"']
    commands += get_run_shim_script(
        is_privileged=is_privileged,
        pjrt_device=pjrt_device,
        bin_path=bin_path,
    )
    return commands


def get_dstack_runner_version() -> str:
    if settings.DSTACK_VERSION is not None:
        return settings.DSTACK_VERSION
    version = os.environ.get("DSTACK_RUNNER_VERSION", None)
    if version is None and settings.DSTACK_USE_LATEST_FROM_BRANCH:
        version = get_latest_runner_build()
    return version or "latest"


def normalize_arch(arch: Optional[str] = None) -> GoArchType:
    """
    Converts the given free-form architecture string to the Go GOARCH format.
    Only 64-bit x86 and ARM are supported. If the word size is not specified (e.g., `x86`, `arm`),
    64-bit is implied.
    If the arch is not specified, falls back to `amd64`.
    """
    if not arch:
        return "amd64"
    arch_lower = arch.lower()
    if "32" in arch_lower or arch_lower in ["i386", "i686"]:
        raise ValueError(f"32-bit architectures are not supported: {arch}")
    if arch_lower.startswith("x86") or arch_lower.startswith("amd"):
        return "amd64"
    if arch_lower.startswith("arm") or arch_lower.startswith("aarch"):
        return "arm64"
    raise ValueError(f"Unsupported architecture: {arch}")


def get_dstack_runner_download_url(arch: Optional[str] = None) -> str:
    url_template = os.environ.get("DSTACK_RUNNER_DOWNLOAD_URL")
    if not url_template:
        if settings.DSTACK_VERSION is not None:
            bucket = "dstack-runner-downloads"
        else:
            bucket = "dstack-runner-downloads-stgn"
        url_template = (
            f"https://{bucket}.s3.eu-west-1.amazonaws.com"
            "/{version}/binaries/dstack-runner-linux-{arch}"
        )
    version = get_dstack_runner_version()
    arch = normalize_arch(arch)
    return url_template.format(version=version, arch=arch)


def get_dstack_shim_download_url(arch: Optional[str] = None) -> str:
    url_template = os.environ.get("DSTACK_SHIM_DOWNLOAD_URL")
    if not url_template:
        if settings.DSTACK_VERSION is not None:
            bucket = "dstack-runner-downloads"
        else:
            bucket = "dstack-runner-downloads-stgn"
        url_template = (
            f"https://{bucket}.s3.eu-west-1.amazonaws.com"
            "/{version}/binaries/dstack-shim-linux-{arch}"
        )
    version = get_dstack_runner_version()
    arch = normalize_arch(arch)
    return url_template.format(version=version, arch=arch)


def get_shim_pre_start_commands(
    base_path: Optional[PathLike] = None,
    bin_path: Optional[PathLike] = None,
    arch: Optional[str] = None,
) -> List[str]:
    url = get_dstack_shim_download_url(arch)
    dstack_shim_binary_path = get_dstack_shim_binary_path(bin_path)
    dstack_working_dir = get_dstack_working_dir(base_path)
    return [
        f"dlpath=$(sudo mktemp -t {DSTACK_SHIM_BINARY_NAME}.XXXXXXXXXX)",
        # -sS -- disable progress meter and warnings, but still show errors (unlike bare -s)
        f'sudo curl -sS --compressed --connect-timeout 60 --max-time 240 --retry 1 --output "$dlpath" "{url}"',
        f'sudo mv "$dlpath" {dstack_shim_binary_path}',
        f"sudo chmod +x {dstack_shim_binary_path}",
        f"sudo mkdir {dstack_working_dir} -p",
    ]


def get_run_shim_script(
    is_privileged: bool,
    pjrt_device: Optional[str],
    bin_path: Optional[PathLike] = None,
) -> List[str]:
    dstack_shim_binary_path = get_dstack_shim_binary_path(bin_path)
    privileged_flag = "--privileged" if is_privileged else ""
    pjrt_device_env = f"--pjrt-device={pjrt_device}" if pjrt_device else ""
    return [
        f"nohup {dstack_shim_binary_path} {privileged_flag} {pjrt_device_env} &",
    ]


def get_gateway_user_data(authorized_key: str) -> str:
    return get_cloud_config(
        package_update=True,
        packages=[
            "nginx",
            "python3.10-venv",
        ],
        snap={"commands": [["install", "--classic", "certbot"]]},
        runcmd=[
            ["ln", "-s", "/snap/bin/certbot", "/usr/bin/certbot"],
            [
                "sed",
                "-i",
                "s/# server_names_hash_bucket_size 64;/server_names_hash_bucket_size 128;/",
                "/etc/nginx/nginx.conf",
            ],
            ["su", "ubuntu", "-c", " && ".join(get_dstack_gateway_commands())],
        ],
        ssh_authorized_keys=[authorized_key],
    )


def get_docker_commands(
    authorized_keys: list[str],
    bin_path: Optional[PathLike] = None,
) -> list[str]:
    dstack_runner_binary_path = get_dstack_runner_binary_path(bin_path)
    authorized_keys_content = "\n".join(authorized_keys).strip()
    commands = [
        # save and unset ld.so variables
        "_LD_LIBRARY_PATH=${LD_LIBRARY_PATH-} && unset LD_LIBRARY_PATH",
        "_LD_PRELOAD=${LD_PRELOAD-} && unset LD_PRELOAD",
        # common functions
        '_exists() { command -v "$1" > /dev/null 2>&1; }',
        # TODO(#1535): support non-root images properly
        "mkdir -p /root && chown root:root /root && export HOME=/root",
        # package manager detection/abstraction
        "_install() { NAME=Distribution; test -f /etc/os-release && . /etc/os-release; echo $NAME not supported; exit 11; }",
        'if _exists apt-get; then _install() { apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y "$1"; }; fi',
        'if _exists yum; then _install() { yum install -y "$1"; }; fi',
        'if _exists apk; then _install() { apk add -U "$1"; }; fi',
        # check in sshd is here, install if not
        "if ! _exists sshd; then _install openssh-server; fi",
        # install curl if necessary
        "if ! _exists curl; then _install curl; fi",
        # create ssh dirs and add public key
        "mkdir -p ~/.ssh",
        "chmod 700 ~/.ssh",
        f"echo '{authorized_keys_content}' > ~/.ssh/authorized_keys",
        "chmod 600 ~/.ssh/authorized_keys",
        # regenerate host keys
        "rm -rf /etc/ssh/ssh_host_*",
        "ssh-keygen -A > /dev/null",
        # Ensure that PRIVSEP_PATH 1) exists 2) empty 3) owned by root,
        # see https://github.com/dstackai/dstack/issues/1999
        # /run/sshd is used in Debian-based distros, including Ubuntu:
        # https://salsa.debian.org/ssh-team/openssh/-/blob/debian/1%259.7p1-7/debian/rules#L60
        # /var/empty is the default path if not configured via ./configure --with-privsep-path=...
        "rm -rf /run/sshd && mkdir -p /run/sshd && chown root:root /run/sshd",
        "rm -rf /var/empty && mkdir -p /var/empty && chown root:root /var/empty",
        # start sshd
        (
            "/usr/sbin/sshd"
            f" -p {DSTACK_RUNNER_SSH_PORT}"
            " -o PidFile=none"
            " -o PasswordAuthentication=no"
            " -o AllowTcpForwarding=yes"
            " -o ClientAliveInterval=30"
            " -o ClientAliveCountMax=4"
        ),
        # restore ld.so variables
        'if [ -n "$_LD_LIBRARY_PATH" ]; then export LD_LIBRARY_PATH="$_LD_LIBRARY_PATH"; fi',
        'if [ -n "$_LD_PRELOAD" ]; then export LD_PRELOAD="$_LD_PRELOAD"; fi',
    ]

    url = get_dstack_runner_download_url()
    commands += [
        f"curl --connect-timeout 60 --max-time 240 --retry 1 --output {dstack_runner_binary_path} {url}",
        f"chmod +x {dstack_runner_binary_path}",
        (
            f"{dstack_runner_binary_path}"
            " --log-level 6"
            " start"
            f" --http-port {DSTACK_RUNNER_HTTP_PORT}"
            f" --ssh-port {DSTACK_RUNNER_SSH_PORT}"
            " --temp-dir /tmp/runner"
            " --home-dir /root"
            " --working-dir /workflow"
        ),
    ]

    return commands


@lru_cache()  # Restart the server to find the latest build
def get_latest_runner_build() -> Optional[str]:
    owner_repo = "dstackai/dstack"
    workflow_id = "build.yml"
    version_offset = 150

    try:
        repo = git.Repo(os.path.abspath(os.path.dirname(__file__)), search_parent_directories=True)
    except git.InvalidGitRepositoryError:
        return None
    for remote in repo.remotes:
        if re.search(rf"[@/]github\.com[:/]{owner_repo}\.", remote.url):
            break
    else:
        return None

    resp = requests.get(
        f"https://api.github.com/repos/{owner_repo}/actions/workflows/{workflow_id}/runs",
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        params={
            "status": "success",
        },
        timeout=10,
    )
    resp.raise_for_status()

    head = repo.head.commit
    for run in resp.json()["workflow_runs"]:
        try:
            if repo.is_ancestor(run["head_sha"], head):
                ver = str(run["run_number"] + version_offset)
                logger.debug("Found the latest runner build: %s", ver)
                return ver
        except git.GitCommandError as e:
            if "Not a valid commit name" not in e.stderr:
                raise
    return None


def get_dstack_gateway_wheel(build: str) -> str:
    channel = "release" if settings.DSTACK_RELEASE else "stgn"
    base_url = f"https://dstack-gateway-downloads.s3.amazonaws.com/{channel}"
    if build == "latest":
        r = requests.get(f"{base_url}/latest-version", timeout=5)
        r.raise_for_status()
        build = r.text.strip()
        logger.debug("Found the latest gateway build: %s", build)
    return f"{base_url}/dstack_gateway-{build}-py3-none-any.whl"


def get_dstack_gateway_commands() -> List[str]:
    build = get_dstack_runner_version()
    return [
        "mkdir -p /home/ubuntu/dstack",
        "python3 -m venv /home/ubuntu/dstack/blue",
        "python3 -m venv /home/ubuntu/dstack/green",
        f"/home/ubuntu/dstack/blue/bin/pip install {get_dstack_gateway_wheel(build)}",
        "sudo /home/ubuntu/dstack/blue/bin/python -m dstack.gateway.systemd install --run",
    ]


def merge_tags(
    base_tags: Dict[str, str],
    backend_tags: Optional[Dict[str, str]] = None,
    resource_tags: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    res = base_tags.copy()
    # backend_tags have priority over resource_tags
    # so that regular users do not override the tags set by admins
    if backend_tags is not None:
        for k, v in backend_tags.items():
            res.setdefault(k, v)
    if resource_tags is not None:
        for k, v in resource_tags.items():
            res.setdefault(k, v)
    return res
