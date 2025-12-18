from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.configurations import RUN_PRIORITY_DEFAULT, ServiceConfiguration
from dstack._internal.core.models.repos.virtual import DEFAULT_VIRTUAL_REPO_ID, VirtualRunRepoData
from dstack._internal.core.models.runs import LEGACY_REPO_DIR, AnyRunConfiguration, RunSpec
from dstack._internal.core.models.volumes import InstanceMountPoint
from dstack._internal.core.services import validate_dstack_resource_name
from dstack._internal.core.services.diff import diff_models
from dstack._internal.server import settings
from dstack._internal.server.models import UserModel
from dstack._internal.server.services.docker import is_valid_docker_volume_target
from dstack._internal.server.services.resources import set_resources_defaults
from dstack._internal.utils.logging import get_logger

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
    if run_spec.run_name is not None:
        validate_dstack_resource_name(run_spec.run_name)
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
        if run_spec.merged_profile.schedule and run_spec.configuration.replicas.min == 0:
            raise ServerClientError(
                "Scheduled services with autoscaling to zero are not supported"
            )
        if len(run_spec.configuration.probes) > settings.MAX_PROBES_PER_JOB:
            raise ServerClientError(
                f"Cannot configure more than {settings.MAX_PROBES_PER_JOB} probes"
            )
        if any(
            p.timeout is not None and p.timeout > settings.MAX_PROBE_TIMEOUT
            for p in run_spec.configuration.probes
        ):
            raise ServerClientError(
                f"Probe timeout cannot be longer than {settings.MAX_PROBE_TIMEOUT}s"
            )
    if run_spec.configuration.priority is None:
        run_spec.configuration.priority = RUN_PRIORITY_DEFAULT
    set_resources_defaults(run_spec.configuration.resources)
    if run_spec.ssh_key_pub is None:
        if user.ssh_public_key:
            run_spec.ssh_key_pub = user.ssh_public_key
        else:
            raise ServerClientError("ssh_key_pub must be set if the user has no ssh_public_key")
    if run_spec.configuration.working_dir is None and legacy_repo_dir:
        run_spec.configuration.working_dir = LEGACY_REPO_DIR


def check_can_update_run_spec(current_run_spec: RunSpec, new_run_spec: RunSpec):
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
    # We don't allow update if the order of archives has been changed, as even if the archives
    # are the same (the same id => hash => content and the same container path), the order of
    # unpacking matters when one path is a subpath of another.
    ignore_files = current_run_spec.file_archives == new_run_spec.file_archives
    _check_can_update_configuration(
        current_run_spec.configuration, new_run_spec.configuration, ignore_files
    )


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
        nodes_required_num = run_spec.configuration.nodes
    elif (
        run_spec.configuration.type == "service"
        and run_spec.configuration.replicas.min is not None
    ):
        nodes_required_num = run_spec.configuration.replicas.min
    return nodes_required_num


def check_run_spec_requires_instance_mounts(run_spec: RunSpec) -> bool:
    return any(
        isinstance(mp, InstanceMountPoint) and not mp.optional
        for mp in run_spec.configuration.volumes
    )


def _check_can_update_configuration(
    current: AnyRunConfiguration, new: AnyRunConfiguration, ignore_files: bool
) -> None:
    if current.type != new.type:
        raise ServerClientError(
            f"Configuration type changed from {current.type} to {new.type}, cannot update"
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
    diff = diff_models(current, new)
    changed_fields = list(diff.keys())
    for key in changed_fields:
        if key not in updatable_fields:
            raise ServerClientError(
                f"Failed to update fields {changed_fields}. Can only update {updatable_fields}"
            )
