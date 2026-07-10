import hashlib
import json
import os
import re
import uuid
from abc import ABC, abstractmethod
from copy import deepcopy
from pathlib import Path
from typing import Any, NoReturn, Optional, Sequence

import gpuhunt
import yaml
from pydantic import ValidationError, parse_obj_as

from dstack._internal.core.models.configurations import (
    DEFAULT_REPLICA_GROUP_NAME,
    ServiceConfiguration,
)
from dstack._internal.core.models.endpoint_presets import (
    EndpointPreset,
    EndpointPresetRecipe,
    EndpointPresetValidation,
    EndpointPresetValidationReplica,
)
from dstack._internal.core.models.envs import EnvSentinel
from dstack._internal.core.models.profiles import ProfileParams
from dstack._internal.core.models.resources import CPUSpec, ResourcesSpec
from dstack._internal.server import settings
from dstack._internal.utils.common import run_async
from dstack._internal.utils.logging import get_logger

_SECRET_ENV_PATTERN = re.compile(r"(token|key|secret|password)", re.IGNORECASE)
logger = get_logger(__name__)


class EndpointPresetService(ABC):
    @abstractmethod
    async def list_presets(self, project_name: str) -> list[EndpointPreset]:
        pass

    @abstractmethod
    async def get_preset(self, project_name: str, base: str) -> Optional[EndpointPreset]:
        pass

    @abstractmethod
    async def delete_preset(self, project_name: str, base: str) -> None:
        pass

    @abstractmethod
    async def save_preset(
        self,
        project_name: str,
        preset: EndpointPreset,
        comments: Optional[Sequence[str]] = None,
    ) -> EndpointPreset:
        """Merge and store a model-level preset."""
        pass


class LocalDirEndpointPresetService(EndpointPresetService):
    def __init__(self, projects_dir: Path = settings.SERVER_PROJECTS_DIR_PATH) -> None:
        self._projects_dir = projects_dir

    async def list_presets(self, project_name: str) -> list[EndpointPreset]:
        return await run_async(self._list_presets, project_name)

    async def get_preset(self, project_name: str, base: str) -> Optional[EndpointPreset]:
        return await run_async(self._get_preset, project_name, base)

    async def delete_preset(self, project_name: str, base: str) -> None:
        return await run_async(self._delete_preset, project_name, base)

    async def save_preset(
        self,
        project_name: str,
        preset: EndpointPreset,
        comments: Optional[Sequence[str]] = None,
    ) -> EndpointPreset:
        return await run_async(self._save_preset, project_name, preset, comments or [])

    def _list_presets(self, project_name: str) -> list[EndpointPreset]:
        return [preset for preset, _ in self._list_merged_presets(project_name)]

    def _get_preset(self, project_name: str, base: str) -> Optional[EndpointPreset]:
        preset, _ = self._find_preset_by_base(project_name, base)
        return preset

    def _delete_preset(self, project_name: str, base: str) -> None:
        _, paths = self._find_preset_by_base(project_name, base)
        if not paths:
            raise FileNotFoundError(base)
        for path in paths:
            path.unlink()

    def _save_preset(
        self,
        project_name: str,
        preset: EndpointPreset,
        comments: Sequence[str],
    ) -> EndpointPreset:
        _validate_preset(preset)
        presets_dir = self._get_project_presets_dir(project_name)
        presets_dir.mkdir(parents=True, exist_ok=True)

        existing_preset, existing_paths = self._find_preset_by_base(project_name, preset.base)
        if existing_preset is not None:
            saved_preset = _merge_presets(existing_preset, preset, prefer_incoming=True)
            path = existing_paths[0]
        else:
            saved_preset = preset
            path = self._get_available_preset_path(presets_dir, preset.base)

        data = _preset_to_data(saved_preset)
        content = _format_preset_comments(comments) + yaml.safe_dump(data, sort_keys=False)
        self._replace_preset_file(presets_dir=presets_dir, path=path, content=content)
        for duplicate_path in existing_paths[1:]:
            duplicate_path.unlink(missing_ok=True)
        loaded_preset = self._load_preset(path)
        if loaded_preset is None:
            raise ValueError(f"saved endpoint preset {path} could not be loaded")
        return loaded_preset

    def _find_preset_by_base(
        self,
        project_name: str,
        base: str,
    ) -> tuple[Optional[EndpointPreset], list[Path]]:
        base_key = base.lower()
        for preset, paths in self._list_merged_presets(project_name):
            if preset.base.lower() == base_key:
                return preset, paths
        return None, []

    def _list_merged_presets(self, project_name: str) -> list[tuple[EndpointPreset, list[Path]]]:
        presets_dir = self._get_project_presets_dir(project_name)
        if not presets_dir.exists():
            return []

        presets_by_base: dict[str, EndpointPreset] = {}
        paths_by_base: dict[str, list[Path]] = {}
        base_order: list[str] = []
        for path in self._iter_preset_paths(presets_dir):
            preset = self._load_preset(path)
            if preset is None:
                continue
            base_key = preset.base.lower()
            existing = presets_by_base.get(base_key)
            if existing is None:
                presets_by_base[base_key] = preset
                paths_by_base[base_key] = [path]
                base_order.append(base_key)
                continue
            try:
                presets_by_base[base_key] = _merge_presets(existing, preset)
            except ValueError as e:
                logger.warning("Skipping endpoint preset %s: %s", path, e)
                continue
            paths_by_base[base_key].append(path)
        return [(presets_by_base[base], paths_by_base[base]) for base in base_order]

    def _iter_preset_paths(self, presets_dir: Path) -> list[Path]:
        return [path for path in sorted(presets_dir.iterdir()) if path.suffix in [".yml", ".yaml"]]

    def _load_preset(self, path: Path) -> Optional[EndpointPreset]:
        try:
            with path.open("r") as f:
                data = yaml.safe_load(f)
            preset = _preset_from_data(data)
            _validate_preset(preset)
            return preset
        except (OSError, ValidationError, ValueError, yaml.YAMLError) as e:
            logger.warning("Skipping endpoint preset %s: %s", path, e)
            return None

    def _get_project_presets_dir(self, project_name: str) -> Path:
        return self._projects_dir / project_name / "presets"

    def _get_available_preset_path(self, presets_dir: Path, model: str) -> Path:
        base_name = _slugify_model(model)
        suffix = 0
        while True:
            name = base_name if suffix == 0 else f"{base_name}-{suffix + 1}"
            path = presets_dir / f"{name}.dstack.yml"
            if not path.exists():
                return path
            suffix += 1

    def _replace_preset_file(self, presets_dir: Path, path: Path, content: str) -> None:
        tmp_path = presets_dir / f".{path.name}.{uuid.uuid4().hex}.tmp"
        tmp_path.write_text(content, encoding="utf-8")
        try:
            os.replace(tmp_path, path)
        finally:
            tmp_path.unlink(missing_ok=True)


_endpoint_preset_service: EndpointPresetService = LocalDirEndpointPresetService()


def get_endpoint_preset_service() -> EndpointPresetService:
    return _endpoint_preset_service


def endpoint_preset_to_api_model(preset: EndpointPreset) -> EndpointPreset:
    return EndpointPreset.parse_obj(preset.dict())


def endpoint_preset_to_api_details(preset: EndpointPreset) -> EndpointPreset:
    return EndpointPreset.parse_obj(preset.dict())


def make_endpoint_preset_recipe_id(service: ServiceConfiguration) -> str:
    service_data = _service_configuration_to_preset_data(service)
    payload = json.dumps(service_data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:8]


def _preset_from_data(data: Any) -> EndpointPreset:
    if not isinstance(data, dict):
        raise ValueError("preset must be a YAML object")
    if data.get("type") != "endpoint-preset":
        raise ValueError("preset must be an endpoint preset")
    base = data.get("base", data.get("model"))
    if not isinstance(base, str) or base == "":
        raise ValueError("preset must specify a base")
    legacy_model = data.get("model")
    if isinstance(legacy_model, str) and "base" in data and legacy_model != base:
        raise ValueError("preset base must match legacy model")
    if "recipes" in data:
        return EndpointPreset(
            base=base,
            recipes=_get_preset_recipes(data=data, base=base),
        )
    return EndpointPreset(
        base=base,
        recipes=[_get_legacy_preset_recipe(data=data, base=base)],
    )


def _get_preset_recipes(data: dict[str, Any], base: str) -> list[EndpointPresetRecipe]:
    raw_recipes = data.get("recipes")
    if not isinstance(raw_recipes, list) or not raw_recipes:
        raise ValueError("preset must specify non-empty recipes")
    recipes = [_get_preset_recipe(raw_recipe, base=base) for raw_recipe in raw_recipes]
    recipe_ids = [recipe.id for recipe in recipes]
    if len(recipe_ids) != len(set(recipe_ids)):
        raise ValueError("preset recipes must have unique ids")
    return recipes


def _get_preset_recipe(raw_recipe: Any, base: str) -> EndpointPresetRecipe:
    if not isinstance(raw_recipe, dict):
        raise ValueError("preset recipes must be objects")
    recipe_id = raw_recipe.get("id")
    if not isinstance(recipe_id, str) or recipe_id == "":
        raise ValueError("preset recipe must specify id")
    recipe_model = raw_recipe.get("model", base)
    if not isinstance(recipe_model, str) or not recipe_model.strip():
        raise ValueError("preset recipe must specify model")
    service_data = _get_service_data(raw_recipe, base=base)
    service = ServiceConfiguration.parse_obj(service_data)
    validations = _get_validations(raw_recipe, service=service)
    return EndpointPresetRecipe(
        id=recipe_id,
        model=recipe_model,
        service=service,
        validations=validations,
    )


def _get_legacy_preset_recipe(data: dict[str, Any], base: str) -> EndpointPresetRecipe:
    service_data = _get_service_data(data, base=base, allow_missing_resources=True)
    raw_groups = _get_legacy_replica_spec_groups(data=data, service_data=service_data)
    _apply_legacy_replica_group_resources(service_data=service_data, groups=raw_groups)
    service = ServiceConfiguration.parse_obj(service_data)
    validation = EndpointPresetValidation(
        replicas=[
            EndpointPresetValidationReplica(
                resources=[
                    ResourcesSpec.parse_obj(resources)
                    for resources in _get_legacy_group_tested_resources(group)
                ]
            )
            for group in raw_groups
        ]
    )
    return EndpointPresetRecipe(
        id=make_endpoint_preset_recipe_id(service),
        model=base,
        service=service,
        validations=[validation],
    )


def _get_service_data(
    data: dict[str, Any],
    base: str,
    allow_missing_resources: bool = False,
) -> dict[str, Any]:
    service_data = data.get("service")
    if not isinstance(service_data, dict):
        raise ValueError("preset recipe must specify a service object")
    service_data = deepcopy(service_data)
    if service_data.get("type") not in (None, "service"):
        raise ValueError("preset service object must be a service configuration")
    if "name" in service_data:
        raise ValueError("preset service object must not specify name")
    profile_fields = sorted(set(ProfileParams.__fields__) & set(service_data))
    if profile_fields:
        raise ValueError(
            "preset service object must not specify profile fields: " + ", ".join(profile_fields)
        )
    if not allow_missing_resources:
        _validate_service_has_resources(service_data)
    service_data.setdefault("model", base)
    service_data["type"] = "service"
    configuration = ServiceConfiguration.parse_obj(service_data)
    if configuration.model is None:
        raise ValueError("preset service configuration must specify model")
    if configuration.model.name.lower() != base.lower():
        raise ValueError("preset base must match the service model")
    return service_data


def _validate_service_has_resources(service_data: dict[str, Any]) -> None:
    replicas = service_data.get("replicas")
    if isinstance(replicas, list):
        for group in replicas:
            if not isinstance(group, dict):
                raise ValueError("preset service replica groups must be objects")
            if "resources" not in group:
                raise ValueError("preset service replica groups must specify resources")
        return
    if "resources" not in service_data:
        raise ValueError("preset service object must specify resources")


def _get_validations(
    raw_recipe: dict[str, Any],
    service: ServiceConfiguration,
) -> list[EndpointPresetValidation]:
    raw_validations = raw_recipe.get("validations")
    if not isinstance(raw_validations, list) or not raw_validations:
        raise ValueError("preset recipe must specify non-empty validations")
    validations = [
        EndpointPresetValidation.parse_obj(raw_validation) for raw_validation in raw_validations
    ]
    _validate_validations(validations=validations, service=service)
    return validations


def _validate_preset(preset: EndpointPreset) -> None:
    if not preset.recipes:
        raise ValueError("preset must specify non-empty recipes")
    recipe_ids = [recipe.id for recipe in preset.recipes]
    if len(recipe_ids) != len(set(recipe_ids)):
        raise ValueError("preset recipes must have unique ids")
    for recipe in preset.recipes:
        if not recipe.model.strip():
            raise ValueError("preset recipe must specify model")
        if recipe.service.model is None:
            raise ValueError("preset recipe service must specify model")
        if recipe.service.model.name.lower() != preset.base.lower():
            raise ValueError("preset base must match the recipe service model")
        _validate_validations(validations=recipe.validations, service=recipe.service)
        _validate_service_gpu_vendor_matches_validations(
            service=recipe.service,
            validations=recipe.validations,
        )


def set_service_gpu_vendors_from_validations(
    service: ServiceConfiguration,
    validations: list[EndpointPresetValidation],
) -> None:
    for group_num, group in enumerate(service.replica_groups):
        resources = group.resources
        if resources is None or not _requires_gpu(resources):
            continue
        validation_vendor = _get_validation_group_gpu_vendor(
            validations=validations,
            group_num=group_num,
        )
        if validation_vendor is None:
            continue
        if resources.gpu is None:
            continue
        if resources.gpu.vendor is not None and resources.gpu.vendor != validation_vendor:
            raise ValueError("preset service GPU vendor does not match validation")
        group_resources = _get_service_group_resources(service, group_num)
        if group_resources.gpu is None:
            continue
        group_resources.gpu.vendor = validation_vendor


def _validate_service_gpu_vendor_matches_validations(
    service: ServiceConfiguration,
    validations: list[EndpointPresetValidation],
) -> None:
    for group_num, group in enumerate(service.replica_groups):
        resources = group.resources
        if resources is None or not _requires_gpu(resources):
            continue
        if resources.gpu is None or resources.gpu.vendor is None:
            continue
        validation_vendor = _get_validation_group_gpu_vendor(
            validations=validations,
            group_num=group_num,
        )
        if validation_vendor is not None and resources.gpu.vendor != validation_vendor:
            raise ValueError("preset service GPU vendor does not match validation")


def _get_validation_group_gpu_vendor(
    validations: list[EndpointPresetValidation],
    group_num: int,
):
    vendors = set()
    for validation in validations:
        for resources in validation.replicas[group_num].resources:
            if resources.gpu is None or resources.gpu.count.min == 0:
                continue
            vendor = _get_validation_resources_gpu_vendor(resources)
            if vendor is not None:
                vendors.add(vendor)
    if len(vendors) > 1:
        raise ValueError("preset validations must not mix GPU vendors in a replica group")
    return next(iter(vendors), None)


def _get_validation_resources_gpu_vendor(resources: ResourcesSpec):
    gpu = resources.gpu
    if gpu is None:
        return None
    if gpu.vendor is not None:
        return gpu.vendor
    if not gpu.name:
        return None
    vendors = {_get_gpu_name_vendor(name) for name in gpu.name}
    vendors.discard(None)
    if len(vendors) > 1:
        raise ValueError("preset validations must not mix GPU vendors in a replica group")
    return next(iter(vendors), None)


def _get_gpu_name_vendor(name: str):
    if _is_known_gpu_name(name, gpuhunt.KNOWN_NVIDIA_GPUS):
        return gpuhunt.AcceleratorVendor.NVIDIA
    if _is_known_gpu_name(name, gpuhunt.KNOWN_AMD_GPUS):
        return gpuhunt.AcceleratorVendor.AMD
    if _is_known_gpu_name(name, gpuhunt.KNOWN_INTEL_ACCELERATORS):
        return gpuhunt.AcceleratorVendor.INTEL
    if _is_known_gpu_name(name, gpuhunt.KNOWN_TENSTORRENT_ACCELERATORS):
        return gpuhunt.AcceleratorVendor.TENSTORRENT
    if name.startswith("tpu-"):
        return gpuhunt.AcceleratorVendor.GOOGLE
    return None


def _is_known_gpu_name(name: str, known_gpus: list) -> bool:
    return any(gpu.name.lower() == name.lower() for gpu in known_gpus)


def _get_service_group_resources(
    service: ServiceConfiguration,
    group_num: int,
) -> ResourcesSpec:
    if isinstance(service.replicas, list):
        resources = service.replicas[group_num].resources
    else:
        resources = service.resources
    if resources is None:
        raise ValueError("preset service object must specify resources")
    return resources


def _requires_gpu(resources: ResourcesSpec) -> bool:
    gpu = resources.gpu
    if gpu is None:
        return False
    if gpu.count.max == 0:
        return False
    return gpu.count.min != 0 or gpu.count.max is not None


def _validate_validations(
    validations: list[EndpointPresetValidation],
    service: ServiceConfiguration,
) -> None:
    expected_group_count = len(service.replica_groups)
    for validation in validations:
        if len(validation.replicas) != expected_group_count:
            raise ValueError("preset validation replicas must match service replica group order")
        for group in validation.replicas:
            if not group.resources:
                raise ValueError("preset validation replicas must specify resources")
            for resources in group.resources:
                _validate_replica_resources_are_exact(resources)


def _merge_presets(
    existing: EndpointPreset,
    incoming: EndpointPreset,
    prefer_incoming: bool = False,
) -> EndpointPreset:
    if existing.base.lower() != incoming.base.lower():
        raise ValueError("cannot merge endpoint presets for different bases")
    recipes = [EndpointPresetRecipe.parse_obj(recipe.dict()) for recipe in existing.recipes]
    recipes_by_id = {recipe.id: recipe for recipe in recipes}
    incoming_recipe_ids = []
    for incoming_recipe in incoming.recipes:
        existing_recipe = recipes_by_id.get(incoming_recipe.id)
        if existing_recipe is None:
            recipe = EndpointPresetRecipe.parse_obj(incoming_recipe.dict())
            recipes.append(recipe)
            recipes_by_id[recipe.id] = recipe
            incoming_recipe_ids.append(recipe.id)
            continue
        if (
            _service_configuration_to_preset_data(existing_recipe.service)
            != (_service_configuration_to_preset_data(incoming_recipe.service))
            or existing_recipe.model != incoming_recipe.model
        ):
            raise ValueError(f"endpoint preset recipe id conflict: {incoming_recipe.id}")
        _merge_recipe_validations(existing_recipe, incoming_recipe.validations)
        incoming_recipe_ids.append(existing_recipe.id)
    if prefer_incoming:
        preferred_ids = set(incoming_recipe_ids)
        recipes = [recipes_by_id[recipe_id] for recipe_id in incoming_recipe_ids] + [
            recipe for recipe in recipes if recipe.id not in preferred_ids
        ]
    return EndpointPreset(base=existing.base, recipes=recipes)


def _merge_recipe_validations(
    recipe: EndpointPresetRecipe,
    incoming_validations: list[EndpointPresetValidation],
) -> None:
    existing_keys = {_validation_key(validation) for validation in recipe.validations}
    for validation in incoming_validations:
        key = _validation_key(validation)
        if key in existing_keys:
            continue
        recipe.validations.append(EndpointPresetValidation.parse_obj(validation.dict()))
        existing_keys.add(key)


def _validation_key(validation: EndpointPresetValidation) -> str:
    data = json.loads(validation.json(exclude_none=True))
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _preset_to_data(preset: EndpointPreset) -> dict[str, Any]:
    return {
        "type": "endpoint-preset",
        "base": preset.base,
        "recipes": [_recipe_to_data(recipe) for recipe in preset.recipes],
    }


def _recipe_to_data(recipe: EndpointPresetRecipe) -> dict[str, Any]:
    return {
        "id": recipe.id,
        "model": recipe.model,
        "service": _service_configuration_to_preset_data(recipe.service),
        "validations": [
            json.loads(validation.json(exclude_none=True)) for validation in recipe.validations
        ],
    }


def _service_configuration_to_preset_data(
    configuration: ServiceConfiguration,
) -> dict[str, Any]:
    service_data = json.loads(configuration.json(exclude_none=True))
    service_data.pop("type", None)
    service_data.pop("name", None)
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
    return service_data


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


def _slugify_model(model: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")
    return slug or "endpoint-preset"


def _get_legacy_replica_spec_groups(
    *,
    data: dict[str, Any],
    service_data: dict[str, Any],
) -> list[dict[str, Any]]:
    raw_groups = data.get("replica_spec_groups")
    if not isinstance(raw_groups, list) or not raw_groups:
        raise ValueError("legacy preset must specify non-empty replica_spec_groups")
    if not all(isinstance(group, dict) for group in raw_groups):
        raise ValueError("legacy preset replica_spec_groups must be objects")
    groups = [_normalize_legacy_replica_spec_group(dict(group)) for group in raw_groups]
    expected_names = _get_expected_replica_group_names(service_data)
    if expected_names == [DEFAULT_REPLICA_GROUP_NAME] and "name" not in groups[0]:
        groups[0]["name"] = DEFAULT_REPLICA_GROUP_NAME
    group_names = [group.get("name") for group in groups]
    if group_names != expected_names:
        raise ValueError(
            "legacy preset replica_spec_groups must match replica group order: "
            + ", ".join(expected_names)
        )
    return groups


def _normalize_legacy_replica_spec_group(group: dict[str, Any]) -> dict[str, Any]:
    if "resources" in group or "tested_resources" in group:
        if "resources" not in group or "tested_resources" not in group:
            raise ValueError(
                "legacy preset replica_spec_groups must specify resources and tested_resources"
            )
        return group
    replica_specs = group.get("replica_specs")
    if not isinstance(replica_specs, list) or not replica_specs:
        raise ValueError("legacy preset replica_spec_groups must specify resources")
    group["resources"] = replica_specs[0]
    group["tested_resources"] = replica_specs
    group.pop("replica_specs", None)
    return group


def _get_expected_replica_group_names(service_data: dict[str, Any]) -> list[str]:
    replicas = service_data.get("replicas")
    if not isinstance(replicas, list):
        return [DEFAULT_REPLICA_GROUP_NAME]
    names = []
    for group in replicas:
        if not isinstance(group, dict):
            raise ValueError("preset service replica groups must be objects")
        name = group.get("name")
        if not isinstance(name, str) or name == "":
            raise ValueError("preset service replica groups must specify names")
        names.append(name)
    return names


def _apply_legacy_replica_group_resources(
    *,
    service_data: dict[str, Any],
    groups: list[dict[str, Any]],
) -> None:
    replicas = service_data.get("replicas")
    if not isinstance(replicas, list):
        service_data["resources"] = groups[0]["resources"]
        return
    resources_by_group = {group["name"]: group["resources"] for group in groups}
    for group in replicas:
        group["resources"] = resources_by_group[group["name"]]


def _get_legacy_group_tested_resources(group: dict[str, Any]) -> list[Any]:
    tested_resources = group.get("tested_resources")
    if not isinstance(tested_resources, list) or not tested_resources:
        raise ValueError("legacy preset group must specify non-empty tested_resources")
    return tested_resources


def _validate_replica_resources_are_exact(resources: ResourcesSpec) -> None:
    cpu = parse_obj_as(CPUSpec, resources.cpu)
    if not _is_exact_range(cpu.count):
        _raise_loose_replica_resources()
    if not _is_exact_range(resources.memory):
        _raise_loose_replica_resources()
    if resources.disk is None or not _is_exact_range(resources.disk.size):
        _raise_loose_replica_resources()
    gpu = resources.gpu
    if gpu is None or not _is_exact_range(gpu.count):
        _raise_loose_replica_resources()
    gpu_count = gpu.count.min
    if gpu_count == 0:
        return
    if gpu.name is None or len(gpu.name) != 1:
        _raise_loose_replica_resources()
    if gpu.memory is None or not _is_exact_range(gpu.memory):
        _raise_loose_replica_resources()
    if gpu.compute_capability is not None:
        _raise_loose_replica_resources()


def _raise_loose_replica_resources() -> NoReturn:
    raise ValueError("preset validations must use exact replica resources")


def _is_exact_range(value) -> bool:
    return (
        value is not None
        and value.min is not None
        and value.max is not None
        and value.min == value.max
    )
