import os
import shutil
import sys
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import TextIO

import yaml
from pydantic import ValidationError

from dstack._internal.cli.models.endpoint_presets import EndpointPreset
from dstack._internal.cli.models.endpoints import (
    MAX_PROMPT_LENGTH,
    EndpointConfiguration,
    EndpointPromptFile,
)
from dstack._internal.cli.services.endpoints.presets import endpoint_preset_to_data
from dstack._internal.cli.utils.common import warn
from dstack._internal.core.errors import CLIError, ConfigurationError
from dstack._internal.utils.common import get_dstack_dir


class EndpointPresetStore:
    """Presets live at `<root>/<preset id>/` — one directory per preset holding
    the artifact (`preset.yaml`) next to the creation session internals.
    Deleted presets are archived under `<root>/.archive/`."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or get_dstack_dir() / "presets"

    def list(self) -> list[EndpointPreset]:
        if not self.root.exists():
            return []
        self._migrate_legacy()
        presets = [self._load(path) for path in self.root.glob("*/preset.yaml")]
        return sorted(presets, key=lambda preset: (preset.base.lower(), preset.id))

    def get(self, preset_id: str) -> EndpointPreset | None:
        _validate_preset_id(preset_id)
        if not self.root.exists():
            return None
        self._migrate_legacy()
        path = self.root / preset_id / "preset.yaml"
        if not path.is_file():
            return None
        preset = self._load(path)
        if preset.id != preset_id:
            raise CLIError(f"Preset file {path} does not match its path")
        return preset

    def save(self, preset: EndpointPreset) -> Path:
        _validate_preset_id(preset.id)
        self._migrate_legacy()
        directory = self.root / preset.id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "preset.yaml"
        content = yaml.safe_dump(endpoint_preset_to_data(preset), sort_keys=False)
        fd, temporary_path = tempfile.mkstemp(
            dir=directory,
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

    def find_by_name(self, name: str) -> EndpointPreset | None:
        for preset in self.list():
            if preset.name == name:
                return preset
        return None

    def release_name(self, name: str) -> EndpointPreset | None:
        """Releases `name` from the preset holding it, keeping the preset."""
        preset = self.find_by_name(name)
        if preset is None:
            return None
        detached = preset.copy(update={"name": None})
        self.save(detached)
        return detached

    def delete(self, preset_id: str) -> bool:
        preset = self.get(preset_id)
        if preset is None:
            return False
        self._archive(self.root / preset_id)
        return True

    def _archive(self, directory: Path) -> None:
        archive_root = self.root / ".archive"
        archive_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        target = archive_root / directory.name
        index = 0
        while target.exists():
            index += 1
            target = archive_root / f"{directory.name}-{index}"
        shutil.move(str(directory), str(target))

    def _migrate_legacy(self) -> None:
        for legacy in list(self.root.glob("models--*/*.yaml")):
            target_dir = self.root / legacy.stem
            target_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            target = target_dir / "preset.yaml"
            if target.exists():
                legacy.unlink()
            else:
                legacy.replace(target)
        for directory in self.root.glob("models--*"):
            with suppress(OSError):
                directory.rmdir()

    def _load(self, path: Path) -> EndpointPreset:
        try:
            with path.open(encoding="utf-8") as f:
                return EndpointPreset.parse_obj(yaml.safe_load(f))
        except (OSError, ValidationError, yaml.YAMLError) as e:
            raise CLIError(f"Invalid preset file {path}: {e}") from e


def _validate_preset_id(preset_id: str) -> None:
    if not preset_id or preset_id.startswith(".") or any(char in preset_id for char in "/\\"):
        raise CLIError(f"Invalid preset ID: {preset_id!r}")


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
            raise ConfigurationError("Preset configuration must be a YAML object")
        configuration = EndpointConfiguration.parse_obj(data)
    except ValidationError as e:
        raise ConfigurationError(e) from e
    except yaml.YAMLError as e:
        raise ConfigurationError(f"Invalid preset configuration: {e}") from e
    model = data.get("model")
    if isinstance(model, dict) and model.get("name") is None:
        key = "base" if "base" in model else "repo"
        warn(
            f"The nested `model.{key}` syntax is deprecated"
            f" unless `model.name` is set. Use top-level `{key}:` instead"
        )
    return configuration


def resolve_endpoint_prompt(
    configuration: EndpointConfiguration, configuration_path: str
) -> str | None:
    """The resolved user prompt text; file paths are relative to the configuration file."""
    if configuration.prompt is None:
        return None
    if isinstance(configuration.prompt, str):
        return configuration.prompt.strip()
    assert isinstance(configuration.prompt, EndpointPromptFile)
    base = Path.cwd() if configuration_path == "-" else Path(configuration_path).parent
    path = base / configuration.prompt.path
    try:
        text = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as e:
        raise ConfigurationError(f"Failed to read the prompt file {path}: {e}") from e
    if not text:
        raise ConfigurationError(f"The prompt file {path} is empty")
    if len(text) > MAX_PROMPT_LENGTH:
        raise ConfigurationError(f"The prompt file {path} exceeds {MAX_PROMPT_LENGTH} characters")
    return text
