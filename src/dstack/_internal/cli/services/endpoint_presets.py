import os
import sys
import tempfile
from pathlib import Path
from typing import List, TextIO

import yaml
from pydantic import ValidationError

from dstack._internal.core.errors import CLIError, ConfigurationError
from dstack._internal.core.models.endpoint_presets import EndpointPreset
from dstack._internal.core.models.endpoints import EndpointConfiguration
from dstack._internal.core.services.endpoint_presets import endpoint_preset_to_data
from dstack._internal.utils.common import get_dstack_dir


class EndpointPresetStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or get_dstack_dir() / "presets"

    def list(self) -> list[EndpointPreset]:
        if not self.root.exists():
            return []
        presets = [self._load(path) for path in self.root.glob("models--*/*.yaml")]
        return sorted(presets, key=lambda preset: (preset.base.lower(), preset.id))

    def get(self, preset_id: str) -> EndpointPreset | None:
        paths = self._find_preset_paths(preset_id)
        if not paths:
            return None
        if len(paths) > 1:
            raise CLIError(f"Endpoint preset ID {preset_id!r} is not unique")
        path = paths[0]
        preset = self._load(path)
        if preset.id != preset_id:
            raise CLIError(f"Endpoint preset file {path} does not match its path")
        return preset

    def save(self, preset: EndpointPreset) -> Path:
        path = self._path(preset.base, preset.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = yaml.safe_dump(endpoint_preset_to_data(preset), sort_keys=False)
        fd, temporary_path = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{preset.id}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary_path, path)
        finally:
            try:
                Path(temporary_path).unlink()
            except FileNotFoundError:
                pass
        return path

    def delete(self, preset_id: str) -> bool:
        preset = self.get(preset_id)
        if preset is None:
            return False
        path = self._path(preset.base, preset.id)
        path.unlink()
        try:
            path.parent.rmdir()
        except OSError:
            pass
        return True

    def delete_for_base(self, base: str) -> int:
        directory = self._directory(base)
        paths = list(directory.glob("*.yaml"))
        presets = [self._load(path) for path in paths]
        if any(preset.base != base for preset in presets):
            raise CLIError(f"Endpoint preset directory {directory} contains another base model")
        for path in paths:
            path.unlink()
        try:
            directory.rmdir()
        except OSError:
            pass
        return len(presets)

    def _load(self, path: Path) -> EndpointPreset:
        try:
            with path.open(encoding="utf-8") as f:
                return EndpointPreset.parse_obj(yaml.safe_load(f))
        except (OSError, ValidationError, yaml.YAMLError) as e:
            raise CLIError(f"Invalid endpoint preset file {path}: {e}") from e

    def _path(self, base: str, preset_id: str) -> Path:
        if not preset_id or any(char in preset_id for char in "/\\"):
            raise CLIError("Endpoint preset ID must not contain path separators")
        return self._directory(base) / f"{preset_id}.yaml"

    def _find_preset_paths(self, preset_id: str) -> List[Path]:
        if not preset_id or any(char in preset_id for char in "/\\"):
            raise CLIError("Endpoint preset ID must not contain path separators")
        return [
            path
            for directory in self.root.glob("models--*")
            if (path := directory / f"{preset_id}.yaml").is_file()
        ]

    def _directory(self, base: str) -> Path:
        directory = "models--" + base.replace("/", "--").replace("\\", "--")
        return self.root / directory


def load_endpoint_configuration(path: str) -> tuple[str, EndpointConfiguration]:
    if path == "-":
        return "-", _parse_endpoint_configuration(sys.stdin)
    configuration_path = Path(path)
    if not configuration_path.is_file():
        raise ConfigurationError(f"Configuration file {path} does not exist")
    try:
        with configuration_path.open(encoding="utf-8") as f:
            configuration = _parse_endpoint_configuration(f)
    except OSError as e:
        raise ConfigurationError(f"Failed to load configuration from {path}") from e
    return str(configuration_path.resolve()), configuration


def _parse_endpoint_configuration(stream: TextIO) -> EndpointConfiguration:
    try:
        data = yaml.safe_load(stream)
        if not isinstance(data, dict):
            raise ConfigurationError("Endpoint configuration must be a YAML object")
        return EndpointConfiguration.parse_obj(data)
    except ValidationError as e:
        raise ConfigurationError(e) from e
    except yaml.YAMLError as e:
        raise ConfigurationError(f"Invalid endpoint configuration: {e}") from e
