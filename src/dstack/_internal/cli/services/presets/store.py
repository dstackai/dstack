import os
import shutil
import tempfile
from pathlib import Path
from typing import TextIO

import yaml
from pydantic import ValidationError

from dstack._internal.cli.models.configurations import (
    MAX_PROMPT_LENGTH,
    PresetConfiguration,
    PresetPromptFile,
)
from dstack._internal.cli.models.presets import PRESET_EXCLUDED_FIELDS, VerifiedPreset
from dstack._internal.cli.services.presets.build import preset_to_yaml_dict
from dstack._internal.cli.utils.common import warn
from dstack._internal.core.errors import CLIError, ConfigurationError
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.utils.common import get_dstack_dir


class EarlierVersionPresetError(CLIError):
    """The file predates dstack 0.21 and cannot be read: that format did not
    record the winning trial."""


class PresetStore:
    """One `<root>/<id>/preset.yml` per preset."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or get_dstack_dir() / "presets"

    def list(self) -> list[VerifiedPreset]:
        if not self.root.exists():
            return []
        presets = []
        earlier_version_ids = []
        for path in self.root.glob("*/preset.yml"):
            try:
                presets.append(self._load(path))
            except EarlierVersionPresetError:
                earlier_version_ids.append(path.parent.name)
            except CLIError as e:
                # One corrupt file must not take down every read; the preset
                # stays deletable by ID. stderr keeps `--json` output parseable.
                warn(str(e), stderr=True)
        if len(earlier_version_ids) == 1:
            warn(
                f"VerifiedPreset {earlier_version_ids[0]} was created before dstack 0.21 and cannot"
                f" be read. Delete it with"
                f" [code]dstack preset delete {earlier_version_ids[0]}[/], or recreate.",
                stderr=True,
            )
        elif earlier_version_ids:
            warn(
                f"{len(earlier_version_ids)} presets created before dstack 0.21 cannot be"
                f" read: {', '.join(sorted(earlier_version_ids))}."
                f" Delete them with [code]dstack preset delete <id>[/], or recreate.",
                stderr=True,
            )
        return sorted(presets, key=lambda preset: (preset.base.lower(), preset.id))

    def get(self, preset_id: str) -> VerifiedPreset | None:
        _validate_preset_id(preset_id)
        if not self.root.exists():
            return None
        path = self.root / preset_id / "preset.yml"
        if not path.is_file():
            return None
        preset = self._load(path)
        if preset.id != preset_id:
            raise CLIError(f"VerifiedPreset file {path} does not match its path")
        return preset

    def save(self, preset: VerifiedPreset) -> Path:
        _validate_preset_id(preset.id)
        directory = self.root / preset.id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "preset.yml"
        # Undo the load-time resolution: paths under the preset directory are saved
        # relative, or re-saving a loaded preset (e.g. `release_name`) would bake
        # this machine's absolute paths back in and break portability.
        preset = preset.model_copy(deep=True)
        for mapping in preset.service.files:
            mapping.local_path = _relative_to_preset_dir(mapping.local_path, directory)
        content = yaml.safe_dump(preset_to_yaml_dict(preset), sort_keys=False)
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

    def find_by_name(self, name: str) -> VerifiedPreset | None:
        for preset in self.list():
            if preset.name == name:
                return preset
        return None

    def find_by_id_or_name(self, ref: str) -> VerifiedPreset | None:
        return self.get(ref) or self.find_by_name(ref)

    def release_name(self, name: str) -> VerifiedPreset | None:
        preset = self.find_by_name(name)
        if preset is None:
            return None
        detached = preset.model_copy(update={"name": None})
        self.save(detached)
        return detached

    def delete(self, preset_id: str) -> bool:
        # Deletes by path so a corrupt preset file is still removable.
        _validate_preset_id(preset_id)
        if not self.root.exists():
            return False
        directory = self.root / preset_id
        if not (directory / "preset.yml").is_file():
            return False
        shutil.rmtree(directory)
        return True

    def _load(self, path: Path) -> VerifiedPreset:
        data = None
        try:
            with path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f)
            upgraded = data
            # `validations` marks the pre-0.21.2 format; the current one
            # stores `verified_on`.
            if isinstance(data, dict) and "validations" in data:
                upgraded = _upgrade_pre_0_21_2_preset(data, preset_id=path.parent.name)
            preset = VerifiedPreset.model_validate(upgraded)
        except (OSError, ValidationError, yaml.YAMLError) as e:
            if isinstance(data, dict) and "validations" in data:
                raise _earlier_version_preset_error(path.parent.name) from e
            raise CLIError(f"Invalid preset file {path}: {e}") from e
        # Paths under the preset directory are saved relative so the directory is
        # portable; resolve them so callers see absolute paths. Files outside it are
        # stored absolute already and pass through.
        for mapping in preset.service.files:
            if not Path(mapping.local_path).is_absolute():
                mapping.local_path = str(path.parent / mapping.local_path)
        return preset


# TODO: Remove in 0.22
def _upgrade_pre_0_21_2_preset(data: dict, *, preset_id: str) -> dict:
    """A preset file from before 0.21.2 stored the service as `service`, the
    verification as `validations`, and echoed the request as top-level fields.
    Everything the old file recorded survives the regrouping; the old format
    never stored a `prompt`, so the upgraded `configuration` cannot carry one."""
    try:
        # The old writer always wrote exactly one validation; its `replicas`
        # entries follow the service's replica group order.
        (validation,) = data["validations"]
        workload = validation["benchmark"]["workload"]
        configuration = {"base": data["base"]}
        for field in ("min_context_length", "max_ttft"):
            if data.get(field) is not None:
                configuration[field] = data[field]
        # The old format never stored the request's workload constraints; the
        # measured workload is its record of them, and without this echo the
        # preset would display today's defaults as its objective.
        if workload.get("dataset", "random") == "random":
            for field in ("input_tokens", "output_tokens", "shared_prefix_tokens"):
                if workload.get(field) is not None:
                    configuration[field] = workload[field]
        else:
            configuration["dataset"] = workload["dataset"]
        if workload.get("concurrency") is not None:
            configuration["concurrency"] = workload["concurrency"]
        # Fields the preset excludes (the applier's deployment choices) would
        # fail validation if an old file carried them.
        service = {
            field: value
            for field, value in data["service"].items()
            if field not in PRESET_EXCLUDED_FIELDS
        }
        # `validations` had no group names; they come from the service itself.
        group_names = [
            group.name for group in ServiceConfiguration.model_validate(service).replica_groups
        ]
        verified_on = [
            {"name": group_names[num], "replicas": replica["resources"]}
            for num, replica in enumerate(validation["replicas"])
        ]
        benchmark = {
            field: value
            for field, value in validation["benchmark"].items()
            # The old format recorded how the benchmark client was wired up;
            # the preset no longer stores that.
            if field not in ("target", "client")
        }
        return {
            "id": data["id"],
            "name": data.get("name"),
            "configuration": configuration,
            "base": data["base"],
            "model": data["model"],
            "context_length": data["context_length"],
            "best_trial": data["trial"],
            # The old format stamped this at save time; the closest fact it
            # recorded for the submission moment.
            "submitted_at": data["created_at"],
            "service": service,
            "benchmark": benchmark,
            "verified_on": verified_on,
        }
    except (KeyError, IndexError, TypeError, AttributeError, ValueError) as e:
        # Even older than the upgradable format (e.g. no `trial` yet), or a
        # file that lost part of its structure.
        raise _earlier_version_preset_error(preset_id) from e


def _earlier_version_preset_error(preset_id: str) -> EarlierVersionPresetError:
    return EarlierVersionPresetError(
        f"VerifiedPreset {preset_id} was created before dstack 0.21 and cannot be read."
        f" Delete it with `dstack preset delete {preset_id}`, or recreate it."
    )


def _relative_to_preset_dir(local_path: str, directory: Path) -> str:
    path = Path(local_path)
    for base in (directory, directory.resolve()):
        try:
            return path.relative_to(base).as_posix()
        except ValueError:
            continue
    return local_path


def _validate_preset_id(preset_id: str) -> None:
    if not preset_id or preset_id.startswith(".") or any(char in preset_id for char in "/\\"):
        raise CLIError(f"Invalid preset ID: {preset_id!r}")


def load_preset_configuration(path: Path) -> PresetConfiguration:
    if not path.is_file():
        raise ConfigurationError(f"Configuration file {path} does not exist")
    try:
        with path.open(encoding="utf-8") as f:
            return parse_preset_configuration(f)
    except OSError as e:
        raise ConfigurationError(f"Failed to load configuration from {path}") from e


def parse_preset_configuration(stream: TextIO) -> PresetConfiguration:
    try:
        data = yaml.safe_load(stream)
        if not isinstance(data, dict):
            raise ConfigurationError("VerifiedPreset configuration must be a YAML object")
        # Only checked here: a stored preset serializes `model` as an object, so
        # the model itself has to keep accepting the form a file may not use.
        model = data.get("model")
        if isinstance(model, dict) and model.get("name") is None:
            key = "base" if "base" in model else "repo"
            raise ConfigurationError(f"Use top-level `{key}:` instead of nested `model.{key}`")
        configuration = PresetConfiguration.model_validate(data)
    except ValidationError as e:
        raise ConfigurationError(e) from e
    except yaml.YAMLError as e:
        raise ConfigurationError(f"Invalid preset configuration: {e}") from e
    return configuration


def resolve_preset_prompt(configuration: PresetConfiguration, base: Path) -> str | None:
    """The prompt text; a prompt file is read relative to `base`."""
    if configuration.prompt is None:
        return None
    if isinstance(configuration.prompt, str):
        return configuration.prompt.strip()
    assert isinstance(configuration.prompt, PresetPromptFile)
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
