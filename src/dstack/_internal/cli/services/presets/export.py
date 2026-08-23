import shutil
from pathlib import Path

import yaml

from dstack._internal.cli.models.presets import AnyStoredPreset
from dstack._internal.core.errors import CLIError, ServerClientError
from dstack._internal.core.services import validate_dstack_resource_name


# TODO: Human-readable service serialization: short syntax, defaults dropped
def export_preset(
    preset: AnyStoredPreset,
    *,
    preset_dir: Path,
    destination: Path,
    force: bool,
    name: str | None = None,
) -> list[Path]:
    """Writes the exact dump of the service at `destination`, changing only
    `name` (from `name` or the preset's name) and the `files` paths; `gateway`
    and profile params are unset by `PortablePreset`, not stripped here.
    Files under `preset_dir` are copied next to `destination` at their
    `preset_dir`-relative paths and `files` is rewritten to match; other files
    pass through absolute. Fails before any write: invalid name, or existing
    targets without `force`. Returns written paths."""
    if name is None:
        name = preset.name
        if name is not None and "/" in name:
            # A pulled copy's local name is the qualified `<project>/<name>`;
            # the registry name after the `/` is a valid resource name by
            # construction, while the qualified form never is.
            name = name.split("/", 1)[1]
    if name is not None:
        try:
            validate_dstack_resource_name(name)
        except ServerClientError as e:
            raise CLIError(str(e)) from e
    service = preset.service.model_copy(deep=True)
    service.name = name
    copies: list[tuple[Path, Path]] = []
    for mapping in service.files:
        source = Path(mapping.local_path)
        # Loading resolved these against the preset directory; a file stored
        # outside it keeps its absolute path and needs no copy.
        if not source.is_relative_to(preset_dir):
            continue
        relative = source.relative_to(preset_dir)
        copies.append((source, destination.parent / relative))
        mapping.local_path = relative.as_posix()
    written = [destination] + [target for _, target in copies]
    if not force:
        for target in written:
            if target.exists():
                raise CLIError(f"{target} already exists. Use --force to overwrite")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(yaml.safe_dump(service.model_dump(mode="json"), sort_keys=False))
    for source, target in copies:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return written
