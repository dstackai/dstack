import io
import os
import shutil
import tarfile
import tempfile
import uuid
from pathlib import Path, PurePosixPath

from dstack._internal.cli.models.presets import PulledPreset
from dstack._internal.cli.services.presets.store import PresetStore
from dstack._internal.cli.utils.common import console, error_console
from dstack._internal.core.errors import (
    CLIError,
    MethodNotAllowedError,
    ResourceNotExistsError,
    ServerClientError,
    URLNotFoundError,
)
from dstack._internal.core.models.presets import (
    PortablePreset,
    PresetArchiveMapping,
    PresetSpec,
    validate_preset_spec_files,
    validate_preset_spec_limits,
)
from dstack._internal.core.services import validate_dstack_resource_name
from dstack._internal.core.services.configs import ConfigManager
from dstack._internal.utils.files import create_file_archive
from dstack.api.server import APIClient

SKY_BASE_URL = "https://sky.dstack.ai"

# The kill switch for the Sky fallback: with it set, only projects from the
# local config resolve.
NO_SKY_FALLBACK_ENV = "DSTACK_NO_SKY_FALLBACK"


def parse_registry_ref(ref: str) -> tuple[str, str]:
    """Splits `<project>/<name|id>` on the first `/`. A ref without `/` is not a
    registry ref; callers decide local vs. registry by its presence."""
    project, separator, rest = ref.partition("/")
    if not separator or not project or not rest:
        # CLIError text is escaped when printed, so backticks, not rich markup.
        raise CLIError(f"Invalid registry reference {ref!r}: expected `<project>/<name|id>`")
    return project, rest


def resolve_registry_client(project: str) -> APIClient:
    """The server hosting the registry a ref points at: the config entry with
    the project's name, or
    Sky with any configured Sky token (dstack tokens are user tokens, so one Sky
    entry authenticates any Sky project the user is a member of)."""
    projects = ConfigManager().list_project_configs()
    for entry in projects:
        if entry.name == project:
            return APIClient(base_url=entry.url, token=entry.token)
    if not os.getenv(NO_SKY_FALLBACK_ENV):
        for entry in projects:
            if entry.url.rstrip("/") == SKY_BASE_URL:
                # The one surprising resolution — a project the config does not
                # know going to a remote default — is the one worth announcing.
                _print_registry_server(SKY_BASE_URL, project)
                return APIClient(base_url=SKY_BASE_URL, token=entry.token)
    raise CLIError(
        f"No server is configured for project {project!r}. Log in with `dstack project add`"
    )


def push_preset_to_registry(store: PresetStore, local_ref: str, registry_ref: str) -> None:
    project, name = parse_registry_ref(registry_ref)
    _validate_registry_name(name)
    preset = store.find_by_id_or_name(local_ref)
    if preset is None:
        raise CLIError(f"Preset {local_ref!r} does not exist")
    if preset.service.registry_auth is not None:
        raise CLIError(
            "The preset service contains registry_auth credentials and cannot be pushed."
            " Remove them from the preset; deployers supply their own registry credentials"
            " at apply time"
        )
    preset_dir = store.root / preset.id
    # The pushed document is the portable preset only: no identity, no
    # creation-session context.
    artifact = PortablePreset(
        **{field: getattr(preset, field) for field in PortablePreset.model_fields}
    ).model_copy(deep=True)
    sources: dict[str, str] = {}
    for mapping in artifact.service.files:
        relative = _relative_pushed_path(mapping.local_path, preset_dir)
        sources.setdefault(relative, mapping.local_path)
        mapping.local_path = relative
    client = resolve_registry_client(project)
    # File contents travel as file archives, the same mechanism run `files`
    # use: content-addressed, deduplicated per user, off-loaded to blob storage
    # where the server has one.
    spec = PresetSpec(
        preset=artifact,
        file_archives=[
            PresetArchiveMapping(id=_upload_archive(client, local_path), path=relative)
            for relative, local_path in sources.items()
        ],
    )
    # The same rules the server enforces, checked here to fail before pushing.
    # The spec is only whole once the archives are uploaded, and the size limit
    # must measure the object the server measures.
    try:
        validate_preset_spec_files(spec)
        validate_preset_spec_limits(spec)
    except ValueError as e:
        raise CLIError(f"Preset {local_ref!r} cannot be pushed: {e}") from e
    try:
        client.presets.push(project, name=name, spec=spec)
    except (URLNotFoundError, MethodNotAllowedError):
        raise _registry_not_supported_error(project, client)
    console.print("OK")


def pull_preset_from_registry(store: PresetStore, registry_ref: str) -> None:
    project, name_or_id = parse_registry_ref(registry_ref)
    client = resolve_registry_client(project)
    try:
        remote = client.presets.get(project, name_or_id)
    except (URLNotFoundError, MethodNotAllowedError):
        raise _registry_not_supported_error(project, client)
    except ResourceNotExistsError as e:
        # The server's detail names the bare ref; the qualified one reads better.
        raise CLIError(f"Preset {registry_ref!r} does not exist") from e
    # `remote.spec` already validated with `extra="ignore"` by the API client, so
    # a preset written by a newer server pulls into an older client unchanged.
    portable = remote.spec.preset
    # The local identity of a pulled preset is its registry id, so re-pulling
    # the same preset overwrites its own copy in place.
    preset_id = str(remote.id)
    file_archives = remote.spec.file_archives
    # The same rules the server enforces on push, re-checked before anything is
    # written locally: relative POSIX, no traversal, no reserved names, no
    # file/directory conflicts, and files and references matching exactly.
    try:
        validate_preset_spec_files(remote.spec)
    except ValueError as e:
        raise CLIError(f"Preset {registry_ref!r} cannot be pulled: {e}") from e
    # The local name is the qualified ref. It can never collide with a locally
    # created preset (local names cannot contain `/`), so the only possible
    # holder is an earlier pull; the name silently moves to the fresh copy,
    # Docker-style. A non-current preset (pulled by id after the name was
    # repointed) must not take the name from the current one — like a Docker
    # pull by digest, it lands untagged.
    qualified_name = f"{project}/{remote.name}"
    local_name = qualified_name if remote.is_current else None
    holder = store.find_by_name(qualified_name)
    if local_name is not None:
        if holder is not None and holder.id != preset_id:
            store.release_name(qualified_name)
    elif holder is not None and holder.id == preset_id:
        # This copy holds the name from an earlier pull, when it was current.
        # Re-pulling it by id must not strip the name off the local store
        # entirely, or local refs to it would stop resolving.
        local_name = qualified_name
    pulled = PulledPreset(
        id=preset_id,
        name=local_name,
        # A pulled preset is dated by the registry it came from.
        created_at=remote.created_at,
        **{field: getattr(portable, field) for field in PortablePreset.model_fields},
    )
    directory = store.root / preset_id
    saved = False
    try:
        # Re-pulling replaces the copy wholesale: a file the preset no longer
        # carries must not survive into the next push.
        shutil.rmtree(directory, ignore_errors=True)
        directory.mkdir(parents=True)
        for mapping in file_archives:
            # Downloaded by id, not by the pulled ref: a name may repoint
            # between requests, and the files must be this preset's.
            blob = client.presets.get_file(project, preset_id, mapping.path)
            _extract_archive(blob, directory / PurePosixPath(mapping.path))
        # Absolute paths under the preset directory, as after a load; save
        # re-relativizes them so the stored file stays portable.
        for mapping in pulled.service.files:
            mapping.local_path = str(directory / mapping.local_path)
        store.save(pulled)
        saved = True
    except (OSError, tarfile.TarError) as e:
        raise CLIError(f"Failed to save preset {registry_ref!r}: {e}") from e
    finally:
        # Any failure - a download error, a rejected archive member, an
        # interrupt - must not leave a directory without its preset document.
        if not saved:
            shutil.rmtree(directory, ignore_errors=True)
    if local_name is not None:
        console.print("OK")
    else:
        console.print(
            f"Pulled [code]{preset_id}[/]; [code]{qualified_name}[/] now names a newer preset"
        )


def _upload_archive(client: APIClient, local_path: str) -> uuid.UUID:
    with tempfile.TemporaryFile("w+b") as fp:
        try:
            archive_hash = create_file_archive(local_path, fp)
        except (OSError, ValueError) as e:
            raise CLIError(f"Failed to archive preset file {local_path}: {e}") from e
        fp.seek(0)
        archive = client.files.upload_archive(hash=archive_hash, fp=fp)
    return archive.id


def _extract_archive(blob: bytes, target: Path) -> None:
    """Extracts an archive produced by `create_file_archive` — its members are
    rooted at the archived path's basename — so the file or directory
    materializes exactly at `target`.

    The server stores archives as opaque blobs, so their members are untrusted
    input from whoever pushed the preset: every member is checked here rather
    than relying on the extraction filter, which older Pythons do not have."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(blob)) as archive:
        members = archive.getmembers()
        for member in members:
            _check_archive_member(member, target)
        try:
            archive.extractall(target.parent, members=members, filter="data")
        except TypeError:
            # Python < 3.10.12 / < 3.11.4 has no extraction filter; the member
            # checks above are what make this safe.
            archive.extractall(target.parent, members=members)  # nosec B202


def _check_archive_member(member: tarfile.TarInfo, target: Path) -> None:
    """Rejects anything that could write outside `target`: a member the archive
    should not carry, a traversing or absolute path, or a link of any kind."""

    def reject(reason: str) -> CLIError:
        return CLIError(
            f"Preset file archive for {target.name!r} carries {reason}: {member.name!r}"
        )

    if not (member.isfile() or member.isdir()):
        # Symlinks and hardlinks can point outside the directory, and their
        # targets are followed by later writes; devices and fifos are never
        # part of a preset.
        raise reject("an unsupported member type")
    name = member.name.replace("\\", "/")
    parts = PurePosixPath(name).parts
    if PurePosixPath(name).is_absolute() or ".." in parts or not parts:
        raise reject("an unsafe member path")
    if parts[0] != target.name:
        raise reject("an unexpected member")


def _print_registry_server(url: str, project: str) -> None:
    # stderr, so `--json` output stays parseable.
    error_console.print(f"Using [code]{url}[/] for [code]{project}[/]")


def _registry_not_supported_error(project: str, client: APIClient) -> CLIError:
    # Naming the server matters: the likely cause is a ref pointing at a project
    # configured against a server that has no registry.
    return CLIError(
        f"The server at {client.base_url} (project {project!r})"
        " does not support the preset registry"
    )


def _relative_pushed_path(local_path: str, preset_dir: Path) -> str:
    path = Path(local_path)
    for base in (preset_dir, preset_dir.resolve()):
        try:
            return path.relative_to(base).as_posix()
        except ValueError:
            continue
    raise CLIError(
        f"Preset file {local_path} is outside the preset directory and cannot be pushed."
        " Move it under the preset directory first"
    )


def _validate_registry_name(name: str) -> None:
    """The same rules the server enforces, checked before uploading: a valid
    resource name that id-first ref resolution can never mistake for an id."""
    try:
        validate_dstack_resource_name(name)
    except ServerClientError as e:
        raise CLIError(str(e)) from e
    try:
        uuid.UUID(name)
    except ValueError:
        return
    raise CLIError("Preset name must not be a UUID")
