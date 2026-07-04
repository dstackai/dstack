import json
import os
import re
import uuid
from abc import ABC, abstractmethod
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional, Sequence

import yaml
from pydantic import ValidationError

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.configurations import (
    DEFAULT_REPLICA_GROUP_NAME,
    ServiceConfiguration,
)
from dstack._internal.core.models.envs import EnvSentinel
from dstack._internal.core.models.profiles import ProfileParams
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.server import settings
from dstack._internal.utils.common import run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

_SECRET_ENV_PATTERN = re.compile(r"(token|key|secret|password)", re.IGNORECASE)


class EndpointPresetReplicaSpecGroup(CoreModel):
    """Ordered to match `ServiceConfiguration.replica_groups`; "0" is the implicit group."""

    name: str
    replica_specs: list[ResourcesSpec]


class EndpointPreset(CoreModel):
    name: str
    model: str
    replica_spec_groups: list[EndpointPresetReplicaSpecGroup]
    """Sorted to match `configuration.replica_groups`; use group name "0" for the implicit group."""
    configuration: ServiceConfiguration


class EndpointPresetService(ABC):
    @abstractmethod
    async def list_presets(self) -> list[EndpointPreset]:
        pass

    @abstractmethod
    async def save_preset(
        self,
        preset: EndpointPreset,
        comments: Optional[Sequence[str]] = None,
    ) -> EndpointPreset:
        """Store a prepared preset and return it with the storage-assigned name."""
        pass


class LocalDirEndpointPresetService(EndpointPresetService):
    def __init__(self, presets_dir: Path = settings.ENDPOINT_PRESETS_DIR) -> None:
        self._presets_dir = presets_dir

    async def list_presets(self) -> list[EndpointPreset]:
        return await run_async(self._list_presets)

    async def save_preset(
        self,
        preset: EndpointPreset,
        comments: Optional[Sequence[str]] = None,
    ) -> EndpointPreset:
        return await run_async(self._save_preset, preset, comments or [])

    def _list_presets(self) -> list[EndpointPreset]:
        if not self._presets_dir.exists():
            return []
        presets = []
        for path in sorted(self._presets_dir.iterdir()):
            if path.suffix not in [".yml", ".yaml"]:
                continue
            preset = self._load_preset(path)
            if preset is not None:
                presets.append(preset)
        return presets

    def _load_preset(self, path: Path) -> Optional[EndpointPreset]:
        try:
            with path.open("r") as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                raise ValueError("preset must be a YAML object")
            if data.get("type") != "endpoint-preset":
                raise ValueError("preset must be an endpoint preset")
            model = data.get("model")
            if not isinstance(model, str) or model == "":
                raise ValueError("preset must specify a model")
            service_data = _get_service_data(data)
            replica_spec_groups = _get_preset_replica_spec_groups(data, service_data)
            service_data.setdefault("model", model)
            service_data["type"] = "service"
            configuration = ServiceConfiguration.parse_obj(service_data)
            if configuration.model is None:
                raise ValueError("preset service configuration must specify model")
            if configuration.model.name.lower() != model.lower():
                raise ValueError("preset model must match the service model")
            return EndpointPreset(
                name=_get_preset_name_from_path(path),
                model=model,
                replica_spec_groups=replica_spec_groups,
                configuration=configuration,
            )
        except (OSError, ValidationError, ValueError, yaml.YAMLError) as e:
            logger.warning("Skipping endpoint preset %s: %s", path, e)
            return None

    def _save_preset(self, preset: EndpointPreset, comments: Sequence[str]) -> EndpointPreset:
        self._presets_dir.mkdir(parents=True, exist_ok=True)
        data = _preset_to_data(preset)
        content = _format_preset_comments(comments) + yaml.safe_dump(data, sort_keys=False)
        base_name = _slugify_preset_name(preset.name)
        suffix = 0
        while True:
            name = base_name if suffix == 0 else f"{base_name}-{suffix + 1}"
            path = self._presets_dir / f"{name}.dstack.yml"
            try:
                self._write_preset_file(path=path, content=content)
                break
            except FileExistsError:
                suffix += 1
        saved_preset = self._load_preset(path)
        if saved_preset is None:
            raise ValueError(f"saved endpoint preset {path} could not be loaded")
        return saved_preset

    def _write_preset_file(self, path: Path, content: str) -> None:
        tmp_path = self._presets_dir / f".{path.name}.{uuid.uuid4().hex}.tmp"
        tmp_path.write_text(content, encoding="utf-8")
        try:
            os.link(tmp_path, path)
        finally:
            tmp_path.unlink(missing_ok=True)


_endpoint_preset_service: EndpointPresetService = LocalDirEndpointPresetService()


def get_endpoint_preset_service() -> EndpointPresetService:
    return _endpoint_preset_service


def _get_preset_name_from_path(path: Path) -> str:
    name = path.stem
    if name.endswith(".dstack"):
        name = name[: -len(".dstack")]
    return name


def _get_service_data(data: dict[str, Any]) -> dict[str, Any]:
    service_data = data.get("service")
    if not isinstance(service_data, dict):
        raise ValueError("preset must specify a service object")
    if service_data.get("type") not in (None, "service"):
        raise ValueError("preset service object must be a service configuration")
    if "name" in service_data:
        raise ValueError("preset service object must not specify name")
    if "resources" in service_data:
        raise ValueError("preset service object must not specify resources")
    profile_fields = sorted(set(ProfileParams.__fields__) & set(service_data))
    if profile_fields:
        raise ValueError(
            "preset service object must not specify profile fields: " + ", ".join(profile_fields)
        )
    _validate_service_replica_groups(service_data)
    return deepcopy(service_data)


def _preset_to_data(preset: EndpointPreset) -> dict[str, Any]:
    return {
        "type": "endpoint-preset",
        "model": preset.model,
        "service": _service_configuration_to_preset_data(preset.configuration),
        "replica_spec_groups": [
            _replica_spec_group_to_data(group) for group in preset.replica_spec_groups
        ],
    }


def _service_configuration_to_preset_data(
    configuration: ServiceConfiguration,
) -> dict[str, Any]:
    service_data = json.loads(configuration.json(exclude_none=True))
    service_data.pop("type", None)
    service_data.pop("name", None)
    service_data.pop("resources", None)
    for field in ProfileParams.__fields__:
        service_data.pop(field, None)
    if configuration.env:
        service_data["env"] = [
            _env_item_to_preset_data(key, value)
            for key, value in sorted(configuration.env.items())
        ]
    else:
        service_data.pop("env", None)
    for field, value in list(service_data.items()):
        if value in ({}, []):
            service_data.pop(field)
    replicas = service_data.get("replicas")
    if isinstance(replicas, list):
        for group in replicas:
            if isinstance(group, dict):
                group.pop("resources", None)
    return service_data


def _replica_spec_group_to_data(group: EndpointPresetReplicaSpecGroup) -> dict[str, Any]:
    return {
        "name": group.name,
        "replica_specs": [
            json.loads(replica_spec.json(exclude_none=True))
            for replica_spec in group.replica_specs
        ],
    }


def _env_item_to_preset_data(key: str, value: str | EnvSentinel) -> str:
    if isinstance(value, EnvSentinel) or _is_secret_like_env(key=key, value=value):
        return key
    return f"{key}={value}"


def _is_secret_like_env(key: str, value: str | EnvSentinel) -> bool:
    if _SECRET_ENV_PATTERN.search(key):
        return True
    return isinstance(value, str) and _SECRET_ENV_PATTERN.search(value) is not None


def _format_preset_comments(comments: Sequence[str]) -> str:
    if not comments:
        return ""
    lines = []
    for comment in comments:
        for line in comment.splitlines() or [""]:
            lines.append(f"# {line}".rstrip())
    return "\n".join(lines) + "\n"


def _slugify_preset_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "endpoint-preset"


def _validate_service_replica_groups(service_data: dict[str, Any]) -> None:
    replicas = service_data.get("replicas")
    if not isinstance(replicas, list):
        return
    for group in replicas:
        if not isinstance(group, dict):
            raise ValueError("preset service replica groups must be objects")
        if "resources" in group:
            raise ValueError("preset service replica groups must not specify resources")


def _get_preset_replica_spec_groups(
    data: dict[str, Any],
    service_data: dict[str, Any],
) -> list[EndpointPresetReplicaSpecGroup]:
    if "resources" in data or "replica_resources" in data:
        raise ValueError("preset must specify replica_spec_groups")
    raw_replica_spec_groups = data.get("replica_spec_groups")
    if not isinstance(raw_replica_spec_groups, list) or not raw_replica_spec_groups:
        raise ValueError("preset must specify non-empty replica_spec_groups")
    if not all(isinstance(group, dict) for group in raw_replica_spec_groups):
        raise ValueError("preset replica_spec_groups must be a list of objects")
    raw_replica_spec_groups = [dict(group) for group in raw_replica_spec_groups]
    expected_names = _get_expected_replica_group_names(service_data)
    if expected_names == [DEFAULT_REPLICA_GROUP_NAME] and "name" not in raw_replica_spec_groups[0]:
        raw_replica_spec_groups[0]["name"] = DEFAULT_REPLICA_GROUP_NAME
    replica_spec_groups = [
        EndpointPresetReplicaSpecGroup.parse_obj(group) for group in raw_replica_spec_groups
    ]
    _validate_replica_spec_groups(
        replica_spec_groups=replica_spec_groups, expected_names=expected_names
    )
    _apply_replica_spec_group_resources(
        service_data=service_data,
        replica_spec_groups=replica_spec_groups,
    )
    return replica_spec_groups


def _get_expected_replica_group_names(service_data: dict[str, Any]) -> list[str]:
    replicas = service_data.get("replicas")
    if not isinstance(replicas, list):
        return [DEFAULT_REPLICA_GROUP_NAME]
    return [_get_replica_group_name(group) for group in replicas]


def _get_replica_group_name(replica_group: Any) -> str:
    if not isinstance(replica_group, dict):
        raise ValueError("preset service replica groups must be objects")
    name = replica_group.get("name")
    if not isinstance(name, str) or name == "":
        raise ValueError(
            "preset service replica groups must specify names when using replica_spec_groups"
        )
    return name


def _validate_replica_spec_groups(
    replica_spec_groups: list[EndpointPresetReplicaSpecGroup],
    expected_names: list[str],
) -> None:
    group_names = [group.name for group in replica_spec_groups]
    if group_names != expected_names:
        raise ValueError(
            "preset replica_spec_groups must match replica group order: "
            + ", ".join(expected_names)
        )
    for group in replica_spec_groups:
        if not group.replica_specs:
            raise ValueError("preset replica_spec_groups must specify non-empty replica_specs")
        first_resources = group.replica_specs[0].dict()
        if any(resources.dict() != first_resources for resources in group.replica_specs):
            raise ValueError("preset replica_specs within one group must have the same resources")


def _apply_replica_spec_group_resources(
    service_data: dict[str, Any],
    replica_spec_groups: list[EndpointPresetReplicaSpecGroup],
) -> None:
    replicas = service_data.get("replicas")
    if not isinstance(replicas, list):
        service_data["resources"] = replica_spec_groups[0].replica_specs[0].dict()
        return
    resources_by_group = {
        group.name: group.replica_specs[0].dict() for group in replica_spec_groups
    }
    for group in replicas:
        group["resources"] = resources_by_group[group["name"]]
