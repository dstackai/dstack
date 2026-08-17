import shutil
from pathlib import Path

import yaml

from dstack._internal.cli.models.presets import VerifiedPreset
from dstack._internal.cli.services.presets.build import service_configuration_to_yaml_dict
from dstack._internal.core.errors import CLIError


def export_preset(
    preset: VerifiedPreset,
    *,
    preset_dir: Path,
    destination: Path,
    force: bool,
) -> list[Path]:
    """Writes the preset's service as a `type: service` configuration at
    `destination` and copies the files it references next to it, keeping their
    relative paths, so the result deploys with plain `dstack apply -f`.
    Returns every path written."""
    service = preset.service.model_copy(deep=True)
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
    destination.write_text(
        yaml.safe_dump(
            {"type": "service", **service_configuration_to_yaml_dict(service)},
            sort_keys=False,
        )
    )
    for source, target in copies:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return written
