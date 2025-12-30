import os
import random
import re
import shlex
import string
import threading
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, List, Optional

import git
import requests
import yaml
from cachetools import TTLCache, cachedmethod
from gpuhunt import CPUArchitecture

from dstack._internal import settings
from dstack._internal.core.backends.base.models import JobConfiguration
from dstack._internal.core.backends.base.offers import OfferModifier, filter_offers_by_requirements
from dstack._internal.core.consts import (
    DSTACK_RUNNER_HTTP_PORT,
    DSTACK_RUNNER_SSH_PORT,
    DSTACK_SHIM_HTTP_PORT,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.compute_groups import ComputeGroup, ComputeGroupProvisioningData
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
from dstack._internal.core.models.routers import AnyRouterConfig
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
DSTACK_SHIM_RESTART_INTERVAL_SECONDS = 3
DSTACK_RUNNER_BINARY_NAME = "dstack-runner"
DEFAULT_PRIVATE_SUBNETS = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
NVIDIA_GPUS_REQUIRING_PROPRIETARY_KERNEL_MODULES = frozenset(
    # All NVIDIA architectures prior to Turing do not support Open Kernel Modules and require
    # proprietary modules. This list is incomplete, update when necessary.
    [
        "v100",
        "p100",
        "p40",
        "p4",
        "m60",
        "m40",
        "m4",
        "k80",
        "k40",
        "k20",
    ]
)


class GoArchType(str, Enum):
    """
    A subset of GOARCH values
    """

    AMD64 = "amd64"
    ARM64 = "arm64"

    def to_cpu_architecture(self) -> CPUArchitecture:
        if self == self.AMD64:
            return CPUArchitecture.X86
        if self == self.ARM64:
            return CPUArchitecture.ARM
        assert False, self


class Compute(ABC):
    """
    A base class for all compute implementations with minimal features.
    If a compute supports additional features, it must also subclass `ComputeWith*` classes.
    """

    @abstractmethod
    def get_offers(self, requirements: Requirements) -> Iterator[InstanceOfferWithAvailability]:
        """
        Returns offers with availability matching `requirements`.
        If the provider is added to gpuhunt, typically gets offers using
        `base.offers.get_catalog_offers()` and extends them with availability info.
        It is called from async code in executor. It can block on call but not between yields.
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
        placement_group: Optional[PlacementGroup],
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


class ComputeWithAllOffersCached(ABC):
    """
    Provides common `get_offers()` implementation for backends
    whose offers do not depend on requirements.
    It caches all offers with availability and post-filters by requirements.
    """

    def __init__(self) -> None:
        super().__init__()
        self._offers_cache_lock = threading.Lock()
        self._offers_cache = TTLCache(maxsize=1, ttl=180)

    @abstractmethod
    def get_all_offers_with_availability(self) -> List[InstanceOfferWithAvailability]:
        """
        Returns all backend offers with availability.
        """
        pass

    def get_offers_modifiers(self, requirements: Requirements) -> Iterable[OfferModifier]:
        """
        Returns functions that modify offers before they are filtered by requirements.
        A modifier function can return `None` to exclude the offer.
        E.g. can be used to set appropriate disk size based on requirements.
        """
        return []

    def get_offers_post_filter(
        self, requirements: Requirements
    ) -> Optional[Callable[[InstanceOfferWithAvailability], bool]]:
        """
        Returns a filter function to apply to offers based on requirements.
        This allows backends to implement custom post-filtering logic for specific requirements.
        """
        return None

    def get_offers(self, requirements: Requirements) -> Iterator[InstanceOfferWithAvailability]:
        cached_offers = self._get_all_offers_with_availability_cached()
        offers = self.__apply_modifiers(cached_offers, self.get_offers_modifiers(requirements))
        offers = filter_offers_by_requirements(offers, requirements)
        post_filter = self.get_offers_post_filter(requirements)
        if post_filter is not None:
            offers = (o for o in offers if post_filter(o))
        return offers

    @cachedmethod(
        cache=lambda self: self._offers_cache,
        lock=lambda self: self._offers_cache_lock,
    )
    def _get_all_offers_with_availability_cached(self) -> List[InstanceOfferWithAvailability]:
        return self.get_all_offers_with_availability()

    @staticmethod
    def __apply_modifiers(
        offers: Iterable[InstanceOfferWithAvailability], modifiers: Iterable[OfferModifier]
    ) -> Iterator[InstanceOfferWithAvailability]:
        for offer in offers:
            for modifier in modifiers:
                offer = modifier(offer)
                if offer is None:
                    break
            else:
                yield offer


class ComputeWithFilteredOffersCached(ABC):
    """
    Provides common `get_offers()` implementation for backends
    whose offers depend on requirements.
    It caches offers using requirements as key.
    """

    def __init__(self) -> None:
        super().__init__()
        self._offers_cache_lock = threading.Lock()
        self._offers_cache = TTLCache(maxsize=10, ttl=180)

    @abstractmethod
    def get_offers_by_requirements(
        self, requirements: Requirements
    ) -> List[InstanceOfferWithAvailability]:
        """
        Returns backend offers with availability matching requirements.
        """
        pass

    def get_offers(self, requirements: Requirements) -> Iterator[InstanceOfferWithAvailability]:
        return iter(self._get_offers_cached(requirements))

    def _get_offers_cached_key(self, requirements: Requirements) -> int:
        # Requirements is not hashable, so we use a hack to get arguments hash
        return hash(requirements.json())

    @cachedmethod(
        cache=lambda self: self._offers_cache,
        key=_get_offers_cached_key,
        lock=lambda self: self._offers_cache_lock,
    )
    def _get_offers_cached(
        self, requirements: Requirements
    ) -> List[InstanceOfferWithAvailability]:
        return self.get_offers_by_requirements(requirements)


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
        placement_group: Optional[PlacementGroup],
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
        return self.create_instance(
            instance_offer, instance_config, placement_group=placement_group
        )

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


class ComputeWithGroupProvisioningSupport(ABC):
    @abstractmethod
    def run_jobs(
        self,
        run: Run,
        job_configurations: List[JobConfiguration],
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
        placement_group: Optional[PlacementGroup],
    ) -> ComputeGroupProvisioningData:
        pass

    @abstractmethod
    def terminate_compute_group(self, compute_group: ComputeGroup):
        pass


class ComputeWithPrivilegedSupport:
    """
    Must be subclassed to support runs with `privileged: true`.
    All VM-based Computes (that is, Computes that use the shim) should subclass this mixin.
    """

    pass


class ComputeWithMultinodeSupport:
    """
    Must be subclassed to support multinode tasks and cluster fleets.
    Instances provisioned in the same project/region must be interconnected.
    """

    pass


class ComputeWithReservationSupport:
    """
    Must be subclassed to support provisioning from reservations.

    The following is expected from a backend that supports reservations:

    - `get_offers` respects `Requirements.reservation` if set, and only returns
      offers that can be provisioned in the configured reservation. It can
      adjust some offer properties such as `availability` and
      `availability_zones` if necessary.
    - `create_instance` respects `InstanceConfig.reservation` if set, and
      provisions the instance in the configured reservation.
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
        """
        pass

    def are_placement_groups_compatible_with_reservations(self, backend_type: BackendType) -> bool:
        """
        Whether placement groups can be used for instances provisioned in reservations.

        Arguments:
            backend_type: matches the backend type of this compute, unless this compute is a proxy
                for other backends (dstack Sky)
        """
        return True


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

    def attach_volume(
        self, volume: Volume, provisioning_data: JobProvisioningData
    ) -> VolumeAttachmentData:
        """
        Attaches a volume to the instance.
        If the volume is not found, it should raise `ComputeError()`.
        Implement only if compute may return `VolumeProvisioningData.attachable`.
        Otherwise, volumes should be attached by `run_job()`.
        """
        raise NotImplementedError()

    def detach_volume(
        self, volume: Volume, provisioning_data: JobProvisioningData, force: bool = False
    ):
        """
        Detaches a volume from the instance.
        Implement only if compute may return `VolumeProvisioningData.detachable`.
        Otherwise, volumes should be detached on instance termination.
        """
        raise NotImplementedError()

    def is_volume_detached(self, volume: Volume, provisioning_data: JobProvisioningData) -> bool:
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
    skip_firewall_setup: bool = False,
    firewall_allow_from_subnets: Iterable[str] = DEFAULT_PRIVATE_SUBNETS,
) -> str:
    shim_commands = get_shim_commands(
        base_path=base_path,
        bin_path=bin_path,
        backend_shim_env=backend_shim_env,
        skip_firewall_setup=skip_firewall_setup,
        firewall_allow_from_subnets=firewall_allow_from_subnets,
    )
    commands = (backend_specific_commands or []) + shim_commands
    return get_cloud_config(
        runcmd=[["sh", "-c", " && ".join(commands)]],
        ssh_authorized_keys=authorized_keys,
    )


def get_shim_env(
    base_path: Optional[PathLike] = None,
    bin_path: Optional[PathLike] = None,
    backend_shim_env: Optional[Dict[str, str]] = None,
    arch: Optional[str] = None,
) -> Dict[str, str]:
    log_level = "5"  # Debug
    envs = {
        "DSTACK_SHIM_HOME": get_dstack_working_dir(base_path),
        "DSTACK_SHIM_HTTP_PORT": str(DSTACK_SHIM_HTTP_PORT),
        "DSTACK_SHIM_LOG_LEVEL": log_level,
        "DSTACK_RUNNER_DOWNLOAD_URL": get_dstack_runner_download_url(arch),
        "DSTACK_RUNNER_BINARY_PATH": get_dstack_runner_binary_path(bin_path),
        "DSTACK_RUNNER_HTTP_PORT": str(DSTACK_RUNNER_HTTP_PORT),
        "DSTACK_RUNNER_SSH_PORT": str(DSTACK_RUNNER_SSH_PORT),
        "DSTACK_RUNNER_LOG_LEVEL": log_level,
    }
    if backend_shim_env is not None:
        envs |= backend_shim_env
    return envs


def get_shim_commands(
    *,
    is_privileged: bool = False,
    pjrt_device: Optional[str] = None,
    base_path: Optional[PathLike] = None,
    bin_path: Optional[PathLike] = None,
    backend_shim_env: Optional[Dict[str, str]] = None,
    arch: Optional[str] = None,
    skip_firewall_setup: bool = False,
    firewall_allow_from_subnets: Iterable[str] = DEFAULT_PRIVATE_SUBNETS,
) -> List[str]:
    commands = get_setup_cloud_instance_commands(
        skip_firewall_setup=skip_firewall_setup,
        firewall_allow_from_subnets=firewall_allow_from_subnets,
    )
    commands += get_shim_pre_start_commands(
        base_path=base_path,
        bin_path=bin_path,
        arch=arch,
    )
    shim_env = get_shim_env(
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


def get_dstack_runner_version() -> Optional[str]:
    if version := settings.DSTACK_VERSION:
        return version
    if version := settings.DSTACK_RUNNER_VERSION:
        return version
    if version_url := settings.DSTACK_RUNNER_VERSION_URL:
        return _fetch_version(version_url)
    if settings.DSTACK_USE_LATEST_FROM_BRANCH:
        return get_latest_runner_build()
    return None


def get_dstack_shim_version() -> Optional[str]:
    if version := settings.DSTACK_VERSION:
        return version
    if version := settings.DSTACK_SHIM_VERSION:
        return version
    if version := settings.DSTACK_RUNNER_VERSION:
        logger.warning(
            "DSTACK_SHIM_VERSION is not set, using DSTACK_RUNNER_VERSION."
            " Future versions will not fall back to DSTACK_RUNNER_VERSION."
            " Set DSTACK_SHIM_VERSION to supress this warning."
        )
        return version
    if version_url := settings.DSTACK_SHIM_VERSION_URL:
        return _fetch_version(version_url)
    if settings.DSTACK_USE_LATEST_FROM_BRANCH:
        return get_latest_runner_build()
    return None


def normalize_arch(arch: Optional[str] = None) -> GoArchType:
    """
    Converts the given free-form architecture string to the Go GOARCH format.
    Only 64-bit x86 and ARM are supported. If the word size is not specified (e.g., `x86`, `arm`),
    64-bit is implied.
    If the arch is not specified, falls back to `amd64`.
    """
    if not arch:
        return GoArchType.AMD64
    arch_lower = arch.lower()
    if "32" in arch_lower or arch_lower in ["i386", "i686"]:
        raise ValueError(f"32-bit architectures are not supported: {arch}")
    if arch_lower.startswith("x86") or arch_lower.startswith("amd"):
        return GoArchType.AMD64
    if arch_lower.startswith("arm") or arch_lower.startswith("aarch"):
        return GoArchType.ARM64
    raise ValueError(f"Unsupported architecture: {arch}")


def get_dstack_runner_download_url(
    arch: Optional[str] = None, version: Optional[str] = None
) -> str:
    url_template = settings.DSTACK_RUNNER_DOWNLOAD_URL
    if not url_template:
        if settings.DSTACK_VERSION is not None:
            bucket = "dstack-runner-downloads"
        else:
            bucket = "dstack-runner-downloads-stgn"
        url_template = (
            f"https://{bucket}.s3.eu-west-1.amazonaws.com"
            "/{version}/binaries/dstack-runner-linux-{arch}"
        )
    if version is None:
        version = get_dstack_runner_version() or "latest"
    return _format_download_url(url_template, version, arch)


def get_dstack_shim_download_url(arch: Optional[str] = None, version: Optional[str] = None) -> str:
    url_template = settings.DSTACK_SHIM_DOWNLOAD_URL
    if not url_template:
        if settings.DSTACK_VERSION is not None:
            bucket = "dstack-runner-downloads"
        else:
            bucket = "dstack-runner-downloads-stgn"
        url_template = (
            f"https://{bucket}.s3.eu-west-1.amazonaws.com"
            "/{version}/binaries/dstack-shim-linux-{arch}"
        )
    if version is None:
        version = get_dstack_shim_version() or "latest"
    return _format_download_url(url_template, version, arch)


def get_setup_cloud_instance_commands(
    skip_firewall_setup: bool,
    firewall_allow_from_subnets: Iterable[str],
) -> list[str]:
    commands = [
        # Workaround for https://github.com/NVIDIA/nvidia-container-toolkit/issues/48
        # Attempts to patch /etc/docker/daemon.json while keeping any custom settings it may have.
        (
            "/bin/sh -c '"  # wrap in /bin/sh to avoid interfering with other cloud init commands
            " grep -q nvidia /etc/docker/daemon.json"
            " && ! grep -q native.cgroupdriver /etc/docker/daemon.json"
            " && jq '\\''.\"exec-opts\" = ((.\"exec-opts\" // []) + [\"native.cgroupdriver=cgroupfs\"])'\\'' /etc/docker/daemon.json > /tmp/daemon.json"
            " && sudo mv /tmp/daemon.json /etc/docker/daemon.json"
            " && sudo service docker restart"
            " || true"
            "'"
        ),
    ]
    if not skip_firewall_setup:
        commands += [
            "ufw --force reset",  # Some OS images have default rules like `allow 80`. Delete them
            "ufw default deny incoming",
            "ufw default allow outgoing",
            "ufw allow ssh",
        ]
        for subnet in firewall_allow_from_subnets:
            commands.append(f"ufw allow from {subnet}")
        commands += [
            "ufw --force enable",
        ]
    return commands


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
    # TODO: Use a proper process supervisor?
    return [
        f"""
        nohup sh -c '
            while true; do
                {dstack_shim_binary_path} {privileged_flag} {pjrt_device_env}
                sleep {DSTACK_SHIM_RESTART_INTERVAL_SECONDS}
            done
        ' &
        """,
    ]


def get_gateway_user_data(authorized_key: str, router: Optional[AnyRouterConfig] = None) -> str:
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
            ["su", "ubuntu", "-c", " && ".join(get_dstack_gateway_commands(router))],
        ],
        ssh_authorized_keys=[authorized_key],
    )


def get_docker_commands(
    authorized_keys: list[str],
    bin_path: Optional[PathLike] = None,
) -> list[str]:
    dstack_runner_binary_path = get_dstack_runner_binary_path(bin_path)
    commands = [
        "( :",
        # See https://github.com/dstackai/dstack/issues/1769
        "unset LD_LIBRARY_PATH && unset LD_PRELOAD",
        # common functions
        'exists() { command -v "$1" > /dev/null 2>&1; }',
        # TODO(#1535): support non-root images properly
        "mkdir -p /root && chown root:root /root && export HOME=/root",
        # package manager detection/abstraction
        "install_pkg() { NAME=Distribution; test -f /etc/os-release && . /etc/os-release; echo $NAME not supported; exit 11; }",
        'if exists apt-get; then install_pkg() { apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y "$1"; }; fi',
        'if exists yum; then install_pkg() { yum install -y "$1"; }; fi',
        'if exists apk; then install_pkg() { apk add -U "$1"; }; fi',
        # check in sshd is here, install if not
        "if ! exists sshd; then install_pkg openssh-server; fi",
        # install curl if necessary
        "if ! exists curl; then install_pkg curl; fi",
        ": )",
    ]

    runner_command = [
        dstack_runner_binary_path,
        "--log-level",
        "6",
        "start",
        "--home-dir",
        "/root",
        "--temp-dir",
        "/tmp/runner",
        "--http-port",
        str(DSTACK_RUNNER_HTTP_PORT),
        "--ssh-port",
        str(DSTACK_RUNNER_SSH_PORT),
    ]
    for authorized_key in authorized_keys:
        runner_command += ["--ssh-authorized-key", authorized_key]

    url = get_dstack_runner_download_url()
    commands += [
        f"curl --connect-timeout 60 --max-time 240 --retry 1 --output {dstack_runner_binary_path} {url}",
        f"chmod +x {dstack_runner_binary_path}",
        shlex.join(runner_command),
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


def get_dstack_gateway_wheel(build: str, router: Optional[AnyRouterConfig] = None) -> str:
    channel = "release" if settings.DSTACK_RELEASE else "stgn"
    base_url = f"https://dstack-gateway-downloads.s3.amazonaws.com/{channel}"
    if build == "latest":
        build = _fetch_version(f"{base_url}/latest-version") or "latest"
        logger.debug("Found the latest gateway build: %s", build)
    wheel = f"{base_url}/dstack_gateway-{build}-py3-none-any.whl"
    # Build package spec with extras if router is specified
    if router:
        return f"dstack-gateway[{router.type}] @ {wheel}"
    return f"dstack-gateway @ {wheel}"


def get_dstack_gateway_commands(router: Optional[AnyRouterConfig] = None) -> List[str]:
    build = get_dstack_runner_version() or "latest"
    gateway_package = get_dstack_gateway_wheel(build, router)
    return [
        "mkdir -p /home/ubuntu/dstack",
        "python3 -m venv /home/ubuntu/dstack/blue",
        "python3 -m venv /home/ubuntu/dstack/green",
        f"/home/ubuntu/dstack/blue/bin/pip install '{gateway_package}'",
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


def requires_nvidia_proprietary_kernel_modules(gpu_name: str) -> bool:
    """
    Returns:
        Whether this NVIDIA GPU requires NVIDIA proprietary kernel modules
        instead of open kernel modules.
    """
    return gpu_name.lower() in NVIDIA_GPUS_REQUIRING_PROPRIETARY_KERNEL_MODULES


def _fetch_version(url: str) -> Optional[str]:
    r = requests.get(url, timeout=5)
    r.raise_for_status()
    version = r.text.strip()
    if not version:
        logger.warning("Empty version response from URL: %s", url)
        return None
    return version


def _format_download_url(template: str, version: str, arch: Optional[str]) -> str:
    return template.format(version=version, arch=normalize_arch(arch).value)
