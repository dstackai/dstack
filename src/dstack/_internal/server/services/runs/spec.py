from typing import Optional

import gpuhunt

from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.configurations import (
    RUN_PRIORITY_DEFAULT,
    SERVICE_HTTPS_DEFAULT,
    ReplicaGroup,
    ServiceConfiguration,
    TaskConfiguration,
)
from dstack._internal.core.models.profiles import ProfileRetry
from dstack._internal.core.models.repos.virtual import DEFAULT_VIRTUAL_REPO_ID, VirtualRunRepoData
from dstack._internal.core.models.resources import GPUSpec, ResourcesSpec
from dstack._internal.core.models.routers import RouterType
from dstack._internal.core.models.runs import LEGACY_REPO_DIR, AnyRunConfiguration, RunSpec
from dstack._internal.core.models.volumes import InstanceMountPoint
from dstack._internal.core.services import validate_dstack_resource_name
from dstack._internal.core.services.diff import ModelDiff, diff_models
from dstack._internal.server import settings
from dstack._internal.server.models import UserModel
from dstack._internal.server.services.docker import is_valid_docker_volume_target
from dstack._internal.server.services.resources import (
    set_default_cpu_spec_arch,
    set_default_gpu_spec,
    set_default_gpu_spec_vendor,
)
from dstack._internal.utils.gpu import detect_gpu_vendors_by_gpu_name
from dstack._internal.utils.interpolator import InterpolatorError
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.nodes_interpolator import (
    contains_groups_ref,
    validate_groups_ref_bounds,
    validate_groups_refs,
)

logger = get_logger(__name__)


_UPDATABLE_SPEC_FIELDS = ["configuration_path", "configuration"]
_TYPE_SPECIFIC_UPDATABLE_SPEC_FIELDS = {
    "service": [
        # rolling deployment
        "repo_data",
        "repo_code_hash",
        "file_archives",
        "working_dir",
    ],
}
_CONF_UPDATABLE_FIELDS = ["priority"]
_TYPE_SPECIFIC_CONF_UPDATABLE_FIELDS = {
    "dev-environment": ["inactivity_duration"],
    "service": [
        # in-place
        "replicas",
        "scaling",
        # rolling deployment
        # NOTE: keep this list in sync with the "Rolling deployment" section in services.md
        "port",
        "probes",
        "resources",
        "volumes",
        "docker",
        "files",
        "image",
        "user",
        "privileged",
        "entrypoint",
        "working_dir",
        "python",
        "nvcc",
        "single_branch",
        "env",
        "shell",
        "commands",
    ],
}


def validate_run_spec_and_set_defaults(
    user: UserModel, run_spec: RunSpec, legacy_repo_dir: bool = False
):
    # This function may set defaults for null run_spec values,
    # although most defaults are resolved when building job_spec
    # so that we can keep both the original user-supplied value (null in run_spec)
    # and the default in job_spec.
    # If a property is stored in job_spec - resolve the default there.
    # Server defaults are preferable over client defaults so that
    # the defaults depend on the server version, not the client version.
    #
    # Callers do not reparse afterwards, so the defaults set here must not touch any field that
    # `ProfileParams` also declares — `run_spec.merged_profile` is computed at parse time and would
    # silently keep the pre-default value. The fields written here (`repo_id`, `repo_data`,
    # `ssh_key_pub`, `configuration.priority`, `configuration.resources`,
    # `configuration.working_dir`) are none of them declared by `ProfileParams`.
    if run_spec.run_name is not None:
        validate_dstack_resource_name(run_spec.run_name)
    _validate_retry_duration(run_spec)
    _validate_groups_ip_refs(run_spec)
    for mount_point in run_spec.configuration.volumes:
        if not is_valid_docker_volume_target(mount_point.path):
            raise ServerClientError(f"Invalid volume mount path: {mount_point.path}")
    if run_spec.repo_id is None and run_spec.repo_data is not None:
        raise ServerClientError("repo_data must not be set if repo_id is not set")
    if run_spec.repo_id is not None and run_spec.repo_data is None:
        raise ServerClientError("repo_id must not be set if repo_data is not set")
    # Some run_spec parameters have to be set here and not in the model defaults since
    # the client may not pass them or pass null, but they must be always present, e.g. for runner.
    if run_spec.repo_id is None:
        run_spec.repo_id = DEFAULT_VIRTUAL_REPO_ID
    if run_spec.repo_data is None:
        run_spec.repo_data = VirtualRunRepoData()
    if (
        run_spec.merged_profile.utilization_policy is not None
        and run_spec.merged_profile.utilization_policy.time_window
        > settings.SERVER_METRICS_RUNNING_TTL_SECONDS
    ):
        raise ServerClientError(
            f"Maximum utilization_policy.time_window is {settings.SERVER_METRICS_RUNNING_TTL_SECONDS}s"
        )
    if isinstance(run_spec.configuration, ServiceConfiguration):
        if run_spec.merged_profile.schedule and all(
            group.count.min == 0 for group in run_spec.configuration.replica_groups
        ):
            raise ServerClientError(
                "Scheduled services with autoscaling to zero are not supported"
            )
        if len(run_spec.configuration.probes or []) > settings.MAX_PROBES_PER_JOB:
            raise ServerClientError(
                f"Cannot configure more than {settings.MAX_PROBES_PER_JOB} probes"
            )
        if any(
            p.timeout is not None and p.timeout > settings.MAX_PROBE_TIMEOUT
            for p in (run_spec.configuration.probes or [])
        ):
            raise ServerClientError(
                f"Probe timeout cannot be longer than {settings.MAX_PROBE_TIMEOUT}s"
            )
    if run_spec.configuration.priority is None:
        run_spec.configuration.priority = RUN_PRIORITY_DEFAULT
    # Homogeneous tasks: keep nodes=1 in stored run_spec so it matches pre-upgrade
    # runs and old clients (Optional nodes defaults to None in the model).
    if (
        isinstance(run_spec.configuration, TaskConfiguration)
        and run_spec.configuration.groups is None
        and run_spec.configuration.nodes is None
    ):
        run_spec.configuration.nodes = 1
    # We do not reject top-level `resources` when `replicas` is a list. Adding strict checks
    # would be fragile because the spec may be changed later (for example by plugins).
    # Same for task `groups`: provisioning uses each group's resources; top-level is not banned.
    set_run_spec_resources_defaults(run_spec)
    _validate_gpu_vendor_and_image(run_spec)
    _validate_cpu_arch_and_image(run_spec)
    if run_spec.ssh_key_pub is None:
        if user.ssh_public_key:
            run_spec.ssh_key_pub = user.ssh_public_key
        else:
            raise ServerClientError("ssh_key_pub must be set if the user has no ssh_public_key")
    if run_spec.configuration.working_dir is None and legacy_repo_dir:
        run_spec.configuration.working_dir = LEGACY_REPO_DIR


def set_run_spec_resources_defaults(run_spec: RunSpec) -> None:
    """Apply resource defaults to a run spec, including GPU vendor and CPU arch inference."""
    configuration = run_spec.configuration
    _set_resources_defaults(
        resources_spec=configuration.resources,
        image=configuration.image,
        docker=configuration.docker,
    )
    if configuration.type == "service" and isinstance(configuration.replicas, list):
        for replica_group in configuration.replicas:
            image, docker = _get_replica_group_image_and_docker(replica_group, configuration)
            _set_resources_defaults(
                resources_spec=replica_group.resources,
                image=image,
                docker=docker,
            )
    elif isinstance(configuration, TaskConfiguration) and configuration.groups is not None:
        image, docker = configuration.image, configuration.docker
        for node_group in configuration.node_groups:
            _set_resources_defaults(
                resources_spec=node_group.resources,
                image=image,
                docker=docker,
            )


def _set_resources_defaults(
    resources_spec: ResourcesSpec, image: Optional[str], docker: Optional[bool]
) -> None:
    gpu_spec = set_default_gpu_spec(resources_spec)
    set_default_cpu_spec_arch(cpu_spec=resources_spec.cpu, gpu_spec=gpu_spec)
    set_default_gpu_spec_vendor(gpu_spec=gpu_spec, image=image, docker=docker)


def _validate_retry_duration(run_spec: RunSpec) -> None:
    retry = run_spec.merged_profile.retry
    if isinstance(retry, ProfileRetry) and retry.duration is not None and retry.duration < 0:
        raise ServerClientError("retry.duration cannot be negative")


def _validate_groups_ip_refs(run_spec: RunSpec) -> None:
    """Validate groups IP refs at submit time (CLI and API).

    Refs are only supported in commands. Typo'd and out-of-range refs are rejected.
    """
    for value in run_spec.configuration.env.values():
        if isinstance(value, str) and contains_groups_ref(value):
            raise ServerClientError(
                "groups IP references are only supported in commands, not in `env`"
            )
    try:
        for command in _iter_configuration_commands(run_spec.configuration):
            validate_groups_refs(command)
        if isinstance(run_spec.configuration, TaskConfiguration):
            group_sizes = [g.nodes for g in run_spec.configuration.node_groups]
            for command in _iter_configuration_commands(run_spec.configuration):
                validate_groups_ref_bounds(command, group_sizes)
    except InterpolatorError as e:
        raise ServerClientError(e.args[0]) from e


def _iter_configuration_commands(configuration: AnyRunConfiguration):
    if isinstance(configuration, TaskConfiguration):
        for group in configuration.node_groups:
            yield from group.commands
        return
    yield from getattr(configuration, "commands", None) or []
    yield from getattr(configuration, "init", None) or []
    if isinstance(configuration, ServiceConfiguration):
        for group in configuration.replica_groups:
            yield from group.commands


def _validate_gpu_vendor_and_image(run_spec: RunSpec) -> None:
    configuration = run_spec.configuration
    vendors: set[gpuhunt.AcceleratorVendor] = set()
    invalid_replicas: list[int] = []
    invalid_groups: list[int] = []
    if configuration.type == "service" and isinstance(configuration.replicas, list):
        for idx, replica_group in enumerate(configuration.replicas):
            image, docker = _get_replica_group_image_and_docker(replica_group, configuration)
            _vendors = _detect_gpu_vendors_requiring_image(
                gpu_spec=replica_group.resources.gpu,
                image=image,
                docker=docker,
            )
            if _vendors:
                vendors.update(_vendors)
                invalid_replicas.append(idx)
    elif isinstance(configuration, TaskConfiguration) and configuration.groups is not None:
        image, docker = configuration.image, configuration.docker
        for idx, node_group in enumerate(configuration.node_groups):
            _vendors = _detect_gpu_vendors_requiring_image(
                gpu_spec=node_group.resources.gpu,
                image=image,
                docker=docker,
            )
            if _vendors:
                vendors.update(_vendors)
                invalid_groups.append(idx)
    else:
        vendors = _detect_gpu_vendors_requiring_image(
            gpu_spec=configuration.resources.gpu,
            image=configuration.image,
            docker=configuration.docker,
        )
    if vendors:
        sorted_vendors = sorted(v.value for v in vendors)
        msg = (
            "`image` must be set when the requested accelerator is not supported by"
            f" the default image: {sorted_vendors}"
        )
        if invalid_replicas:
            msg = f"replicas{invalid_replicas}: {msg}"
        elif invalid_groups:
            msg = f"groups{invalid_groups}: {msg}"
        raise ServerClientError(msg)


def _detect_gpu_vendors_requiring_image(
    gpu_spec: Optional[GPUSpec], image: Optional[str], docker: Optional[bool]
) -> set[gpuhunt.AcceleratorVendor]:
    if image is not None or docker:
        return set()
    if gpu_spec is None or gpu_spec.count.max == 0:
        return set()
    vendors: set[gpuhunt.AcceleratorVendor] = set()
    if gpu_spec.vendor is not None:
        vendors.add(gpu_spec.vendor)
    else:
        # Unknown models are ignored (loose validation -- skips possible models that
        # won't work with the default dstack image). The other option would be to treat them as
        # non-NVIDIA, forcing the user to set `image`, even if they actually are NVIDIA (overly
        # strict validation)
        for gpu_name in gpu_spec.name or []:
            vendors.update(detect_gpu_vendors_by_gpu_name(gpu_name))
    # * NVIDIA definitely works with our image -- it's built for NVIDIA
    # * Google TPU should work with our image -- all dependencies may be installed from PyPI, there
    #   are no vendors dependencies that must be preinstalled/shipped with the image; basically,
    #    our image is just Ubuntu + pip (uv) for TPU workloads
    # * AMD, Intel Gaudi, Tenstorrent rely on some pinned system packages and/or patched libraries
    #   and ship their own images -- we don't expect them to work on our generic
    #   Ubuntu + CUDA image
    return vendors - {gpuhunt.AcceleratorVendor.NVIDIA, gpuhunt.AcceleratorVendor.GOOGLE}


def _validate_cpu_arch_and_image(run_spec: RunSpec) -> None:
    image_msg = "`image` must be set when ARM CPU requested"
    docker_msg = "`docker: true` is not supported on ARM CPU"
    configuration = run_spec.configuration
    if configuration.type == "service" and isinstance(configuration.replicas, list):
        invalid_replicas_without_image: list[int] = []
        invalid_replicas_with_docker: list[int] = []
        for idx, replica_group in enumerate(configuration.replicas):
            image, docker = _get_replica_group_image_and_docker(replica_group, configuration)
            if replica_group.resources.cpu.arch == gpuhunt.CPUArchitecture.ARM:
                if docker:
                    invalid_replicas_with_docker.append(idx)
                elif image is None:
                    invalid_replicas_without_image.append(idx)
        errors: list[str] = []
        if invalid_replicas_without_image:
            errors.append(f"replicas{invalid_replicas_without_image}: {image_msg}")
        if invalid_replicas_with_docker:
            errors.append(f"replicas{invalid_replicas_with_docker}: {docker_msg}")
        if errors:
            raise ServerClientError("\n".join(errors))
    elif isinstance(configuration, TaskConfiguration) and configuration.groups is not None:
        image, docker = configuration.image, configuration.docker
        invalid_groups_without_image: list[int] = []
        invalid_groups_with_docker: list[int] = []
        for idx, node_group in enumerate(configuration.node_groups):
            if node_group.resources.cpu.arch == gpuhunt.CPUArchitecture.ARM:
                if docker:
                    invalid_groups_with_docker.append(idx)
                elif image is None:
                    invalid_groups_without_image.append(idx)
        errors: list[str] = []
        if invalid_groups_without_image:
            errors.append(f"groups{invalid_groups_without_image}: {image_msg}")
        if invalid_groups_with_docker:
            errors.append(f"groups{invalid_groups_with_docker}: {docker_msg}")
        if errors:
            raise ServerClientError("\n".join(errors))
    elif configuration.resources.cpu.arch == gpuhunt.CPUArchitecture.ARM:
        if configuration.docker:
            raise ServerClientError(docker_msg)
        if configuration.image is None:
            raise ServerClientError(image_msg)


def _get_replica_group_image_and_docker(
    replica_group: ReplicaGroup, configuration: ServiceConfiguration
) -> tuple[Optional[str], Optional[bool]]:
    image = replica_group.image
    if image is None:
        image = configuration.image
    docker = replica_group.docker
    if docker is None:
        docker = configuration.docker
    return image, docker


def _check_dynamo_in_place_update_compatibility(
    current_run_spec: RunSpec, new_run_spec: RunSpec
) -> None:
    """Reject in-place updates that would re-provision a Dynamo router.

    Workers cache the router internal IP at provisioning time; changes that
    trigger a rolling router update must not be applied in place.
    """
    current_cfg = current_run_spec.configuration
    new_cfg = new_run_spec.configuration
    if not isinstance(current_cfg, ServiceConfiguration) or not isinstance(
        new_cfg, ServiceConfiguration
    ):
        return

    current_router_group = next(
        (g for g in current_cfg.replica_groups if g.router is not None), None
    )
    new_router_group = next((g for g in new_cfg.replica_groups if g.router is not None), None)
    current_router_type = (
        current_router_group.router.type
        if current_router_group is not None and current_router_group.router is not None
        else None
    )
    new_router_type = (
        new_router_group.router.type
        if new_router_group is not None and new_router_group.router is not None
        else None
    )
    if (
        current_router_type is not None
        and new_router_type is not None
        and current_router_type != new_router_type
    ):
        raise ServerClientError(
            "Cannot change router.type in place. Stop the run with `dstack stop` and re-apply."
        )
    if RouterType.DYNAMO not in (current_router_type, new_router_type):
        return
    if current_router_group != new_router_group:
        raise ServerClientError(
            "Cannot update a Dynamo router replica group in place. "
            "Stop the run with `dstack stop` and re-apply."
        )
    _router_affecting_top_level_fields = tuple(
        f
        for f in _TYPE_SPECIFIC_CONF_UPDATABLE_FIELDS.get("service", [])
        if f not in ("replicas", "scaling")
    )
    for field in _router_affecting_top_level_fields:
        if getattr(current_cfg, field, None) != getattr(new_cfg, field, None):
            raise ServerClientError(
                f"Cannot change top-level `{field}` in place when the "
                f"service has a Dynamo router (would re-provision the "
                f"router and invalidate workers' cached "
                f"DSTACK_ROUTER_INTERNAL_IP). Stop the run with "
                f"`dstack stop` and re-apply."
            )
    for field in _TYPE_SPECIFIC_UPDATABLE_SPEC_FIELDS.get("service", []):
        if getattr(current_run_spec, field, None) != getattr(new_run_spec, field, None):
            raise ServerClientError(
                f"Cannot change top-level `{field}` in place when the "
                f"service has a Dynamo router (would re-provision the "
                f"router and invalidate workers' cached "
                f"DSTACK_ROUTER_INTERNAL_IP). Stop the run with "
                f"`dstack stop` and re-apply."
            )


def check_can_update_run_spec(current_run_spec: RunSpec, new_run_spec: RunSpec) -> ModelDiff:
    """
    Check if in-place update is possible.

    Returns the diff if it is possible.
    Raises ServerClientError otherwise.
    """
    spec_diff = diff_models(current_run_spec, new_run_spec)
    changed_spec_fields = list(spec_diff.keys())
    updatable_spec_fields = _UPDATABLE_SPEC_FIELDS + _TYPE_SPECIFIC_UPDATABLE_SPEC_FIELDS.get(
        new_run_spec.configuration.type, []
    )
    for key in changed_spec_fields:
        if key not in updatable_spec_fields:
            raise ServerClientError(
                f"Failed to update fields {changed_spec_fields}."
                f" Can only update {updatable_spec_fields}."
            )
    _check_dynamo_in_place_update_compatibility(current_run_spec, new_run_spec)
    # We don't allow update if the order of archives has been changed, as even if the archives
    # are the same (the same id => hash => content and the same container path), the order of
    # unpacking matters when one path is a subpath of another.
    ignore_files = current_run_spec.file_archives == new_run_spec.file_archives
    spec_diff["configuration"] = _check_can_update_configuration(
        current_run_spec.configuration, new_run_spec.configuration, ignore_files
    )
    return spec_diff


def can_update_run_spec(current_run_spec: RunSpec, new_run_spec: RunSpec) -> bool:
    try:
        check_can_update_run_spec(current_run_spec, new_run_spec)
    except ServerClientError as e:
        logger.debug("Run cannot be updated: %s", repr(e))
        return False
    return True


def get_nodes_required_num(run_spec: RunSpec) -> int:
    nodes_required_num = 1
    if run_spec.configuration.type == "task":
        nodes_required_num = run_spec.configuration.nodes_num
    elif run_spec.configuration.type == "service":
        nodes_required_num = sum(
            group.count.min or 0 for group in run_spec.configuration.replica_groups
        )
    return nodes_required_num


def check_run_spec_requires_instance_mounts(run_spec: RunSpec) -> bool:
    return any(
        isinstance(mp, InstanceMountPoint) and not mp.optional
        for mp in run_spec.configuration.volumes
    )


def _check_can_update_configuration(
    current: AnyRunConfiguration, new: AnyRunConfiguration, ignore_files: bool
) -> ModelDiff:
    """
    Check if in-place update is possible.

    Returns the diff if it is possible.
    Raises ServerClientError otherwise.
    """
    if current.type != new.type:
        raise ServerClientError(
            f"Configuration type changed from {current.type} to {new.type}, cannot update"
        )

    if isinstance(current, ServiceConfiguration) and isinstance(new, ServiceConfiguration):
        current_router_group = next(
            (g for g in current.replica_groups if g.router is not None), None
        )
        new_router_group = next((g for g in new.replica_groups if g.router is not None), None)
        current_router_group_name = (
            current_router_group.name if current_router_group is not None else None
        )
        new_router_group_name = new_router_group.name if new_router_group is not None else None
        if current_router_group_name != new_router_group_name:
            raise ServerClientError(
                "Cannot update router replica groups in-place (adding/removing `router` or changing "
                "which replica group is the router is not supported). Stop the run and apply again."
            )
    updatable_fields = _CONF_UPDATABLE_FIELDS + _TYPE_SPECIFIC_CONF_UPDATABLE_FIELDS.get(
        new.type, []
    )
    if ignore_files:
        # We ignore files diff if the file archives are the same. It allows the user to move
        # local files/dirs as long as their name(*), content, and the container path stay the same.
        # (*) We could also ignore local name changes if the names didn't change in the tarballs.
        # Currently, the client preserves the original file/dir name it the tarball, but it could
        # use some generic names like "file"/"directory" instead.
        updatable_fields.append("files")
    if (
        isinstance(current, ServiceConfiguration)
        and isinstance(new, ServiceConfiguration)
        and current.https in (None, SERVICE_HTTPS_DEFAULT)
        and new.https in (None, SERVICE_HTTPS_DEFAULT)
    ):
        # Allow switching between `https: <explicit-default>` and unset `https`. Has no effect.
        updatable_fields.append("https")
    diff = diff_models(current, new)
    changed_fields = list(diff.keys())
    for key in changed_fields:
        if key not in updatable_fields:
            raise ServerClientError(
                f"Failed to update fields {changed_fields}. Can only update {updatable_fields}"
            )
    return diff
