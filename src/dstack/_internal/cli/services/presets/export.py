import shutil
from pathlib import Path

import yaml

from dstack._internal.cli.models.presets import VerifiedPreset
from dstack._internal.cli.services.presets.build import service_configuration_to_yaml_dict
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.files import FilePathMapping


def export_preset(
    preset: VerifiedPreset,
    *,
    preset_dir: Path,
    destination: Path,
    force: bool,
) -> list[Path]:
    """Writes the preset's service as a `type: service` configuration at
    `destination` and copies the files it references next to it, so the result
    deploys with plain `dstack apply -f`. Returns every path written."""
    service = preset.service.model_copy(deep=True)
    stored: list[FilePathMapping] = []
    record_paths: list[Path] = []
    for mapping in service.files:
        source = Path(mapping.local_path)
        # Loading resolved these against the preset directory; a file stored
        # outside it keeps its absolute path and needs no copy.
        if not source.is_relative_to(preset_dir):
            continue
        stored.append(mapping)
        record_paths.append(source.relative_to(preset_dir))
    exported_paths = [_without_record_prefix(path) for path in record_paths]
    if _collides(exported_paths, record_paths, destination):
        exported_paths = record_paths
    copies: list[tuple[Path, Path]] = []
    for mapping, record_path, exported_path in zip(stored, record_paths, exported_paths):
        copies.append((preset_dir / record_path, destination.parent / exported_path))
        mapping.local_path = exported_path.as_posix()
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


def _without_record_prefix(relative: Path) -> Path:
    """The store keeps a service's files inside the session records it mirrors,
    `service/<k>/` (final-service attempt) or `trials/<n>/`; the numbering is
    internal, so the export keeps only the structure under it:
    `service/2/patches/fix.patch` exports as `patches/fix.patch`."""
    if (
        len(relative.parts) > 2
        and relative.parts[0] in ("service", "trials")
        and relative.parts[1].isdigit()
    ):
        return Path(*relative.parts[2:])
    return relative


def _collides(exported_paths: list[Path], record_paths: list[Path], destination: Path) -> bool:
    """Whether dropping the record prefixes would land two different files on
    one exported path, or a file on the configuration itself; the full record
    layout is kept in that case. Compared case-insensitively so an export
    cannot silently overwrite itself on a case-insensitive filesystem."""
    record_by_export: dict[str, Path] = {}
    for record_path, exported_path in zip(record_paths, exported_paths):
        key = exported_path.as_posix().casefold()
        if key == destination.name.casefold():
            return True
        if record_by_export.setdefault(key, record_path) != record_path:
            return True
    return False
