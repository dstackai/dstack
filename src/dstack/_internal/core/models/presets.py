import re
from typing import Any, List, Literal, Optional, Sequence, Union

from pydantic import Field, PositiveFloat, PositiveInt, field_validator, model_validator
from typing_extensions import Annotated, Self

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.configurations import (
    PresetModelSpec,
    ServiceConfiguration,
)
from dstack._internal.core.models.files import FileArchiveMapping
from dstack._internal.core.models.profiles import ProfileParams
from dstack._internal.core.models.resources import Range, ResourcesSpec

# These models cannot live in `core/models/presets.py`: `core/models/configurations.py`
# imports `PresetConfiguration` from it, so importing `ServiceConfiguration` back would
# be a cycle. Nothing imports this sibling module from `configurations.py`.

# Enforced by the server; the client checks before pushing to fail fast. File
# contents travel as file archives (the same mechanism run `files` use), so
# their sizes are governed by the files service, not here.
MAX_PRESET_SPEC_SIZE = 1 * 1024 * 1024
MAX_PRESET_FILES = 100

# The service name, the gateway, and the profile parameters are chosen by whoever
# runs `dstack apply` with the preset, so a preset never carries them.
PRESET_EXCLUDED_FIELDS = ("name", "gateway", *ProfileParams.model_fields)

# The local store keeps the preset document at this path inside the preset
# directory, so a pushed file must never claim it.
_RESERVED_PRESET_FILE_PATHS = frozenset({"preset.yml"})


class PresetWorkload(CoreModel):
    # A Literal, not a str: the agent-facing JSON schema is generated from this
    # model, so the allowed values must be part of it.
    api: Literal["chat_completions", "completions"]
    dataset: str
    num_requests: PositiveInt
    input_tokens: PositiveInt
    output_tokens: Annotated[int, Field(ge=2)]
    concurrency: PositiveInt


class PresetRandomWorkload(PresetWorkload):
    # A Literal, not a defaulted str: `PresetBenchmark.workload` is a union with
    # the base model, and only a literal `dataset` discriminates it.
    dataset: Literal["random"] = "random"
    shared_prefix_tokens: Annotated[int, Field(ge=0)] = 0


class PresetBenchmarkLatency(CoreModel):
    mean: Annotated[float, Field(ge=0)]
    p50: Annotated[float, Field(ge=0)]
    p99: Annotated[float, Field(ge=0)]


class PresetBenchmarkMetrics(CoreModel):
    successful_requests: Annotated[int, Field(ge=0)]
    failed_requests: Annotated[int, Field(ge=0)]
    duration_seconds: PositiveFloat
    total_input_tokens: Annotated[int, Field(ge=0)]
    total_output_tokens: Annotated[int, Field(ge=0)]
    # Stored as reported, but never read back: `effective_*` recomputes both
    # from the totals rather than trusting self-reported rates.
    output_tok_per_s: PositiveFloat
    per_user_tok_per_s: PositiveFloat
    ttft_ms: PresetBenchmarkLatency
    tpot_ms: PresetBenchmarkLatency


class PresetBenchmark(CoreModel):
    """The agent reports its benchmark in exactly this shape, and is forced to by
    the schema generated from it. Changing a field here means also changing the
    `## Benchmark` section of the system prompt, which tells it what to put there."""

    tool: Annotated[str, Field(min_length=1)]
    tool_version: Annotated[str, Field(min_length=1)]
    command: Annotated[str, Field(min_length=1)]
    # The subclass first: a report without `dataset` is a random workload, and a
    # base-typed field would reject its `shared_prefix_tokens` as unknown.
    workload: Union[PresetRandomWorkload, PresetWorkload]
    metrics: PresetBenchmarkMetrics

    @property
    def effective_output_tok_per_s(self) -> float:
        return self.metrics.total_output_tokens / self.metrics.duration_seconds

    @property
    def effective_per_user_tok_per_s(self) -> float:
        return 1000 / self.metrics.tpot_ms.mean

    @field_validator("command")
    @classmethod
    def validate_command_has_no_bearer_token(cls, value: str) -> str:
        for match in re.finditer(r"(?i)\bbearer\s+([^\s\"']+)", value):
            token = match.group(1)
            if token.startswith("$") or "redacted" in token.lower() or set(token) == {"*"}:
                continue
            # Prose such as "auth via bearer header from env" is not a
            # credential: only credential-shaped values are rejected.
            if len(token) < 16 or not any(char.isdigit() for char in token):
                continue
            raise ValueError("command must not contain a bearer token value")
        return value

    @model_validator(mode="after")
    def validate_metrics(self) -> Self:
        if self.metrics.failed_requests != 0:
            raise ValueError("benchmark must not include failed requests")
        if self.metrics.successful_requests != self.workload.num_requests:
            raise ValueError("benchmark request count must match workload.num_requests")
        return self


class PresetVerificationReplicaGroup(CoreModel):
    # The service replica group this was measured for.
    name: str
    # One entry per replica that was running: its actual resources.
    replicas: List[ResourcesSpec]


class PortablePreset(CoreModel):
    """A preset that carries everything needed to deploy it and nothing tied to
    where it is stored."""

    # The base model family.
    base: Annotated[str, Field(min_length=1)]
    # The exact repo/path the service loads, which `base` is a variant of. Not
    # the client-facing API model name — that is `service.model`.
    repo: Annotated[str, Field(min_length=1)]
    # The largest context the service was verified to serve.
    context_length: PositiveInt
    # The verified run's spec configuration. The validator below keeps `name`,
    # `gateway`, and profile params unset (the deployer's choices) and requires
    # `model` and resources. Env keys the user declared as passthroughs hold
    # `EnvSentinel` references, not the resolved secrets; other env values are
    # stored as-is. `files` paths are stored relative to the preset directory,
    # absolute after load.
    service: ServiceConfiguration
    benchmark: PresetBenchmark
    # The hardware it was verified on: the actual resources of every running
    # replica, by service replica group.
    verified_on: List[PresetVerificationReplicaGroup]

    @model_validator(mode="after")
    def validate_artifact(self) -> Self:
        service = self.service
        if service.model is None:
            raise ValueError("preset service must specify model")
        if any(group.resources is None for group in service.replica_groups):
            raise ValueError("preset service must specify resources")
        for field in PRESET_EXCLUDED_FIELDS:
            if getattr(service, field) is not None:
                raise ValueError(f"preset service must not specify {field}")
        if [group.name for group in self.verified_on] != [
            group.name for group in service.replica_groups
        ]:
            raise ValueError("preset verification replica groups must match the service's")
        for replica_group in self.verified_on:
            if not replica_group.replicas:
                raise ValueError("preset verification replica groups must not be empty")
            for resources in replica_group.replicas:
                _validate_exact_resources(resources)
        return self


def _validate_exact_resources(resources: ResourcesSpec) -> None:
    cpu = resources.cpu
    if not _is_exact(cpu.count) or not _is_exact(resources.memory):
        raise ValueError("preset verification resources must be exact")
    if resources.disk is None or not _is_exact(resources.disk.size):
        raise ValueError("preset verification resources must be exact")
    gpu = resources.gpu
    if gpu is None or not _is_exact(gpu.count):
        raise ValueError("preset verification resources must be exact")
    if gpu.count.min == 0:
        return
    if gpu.name is None or len(gpu.name) != 1 or not _is_exact(gpu.memory):
        raise ValueError("preset verification resources must be exact")


def _is_exact(value: Optional[Range]) -> bool:
    return (
        value is not None
        and value.min is not None
        and value.max is not None
        and value.min == value.max
    )


def validate_preset_file_path(path: str) -> None:
    """Raises ValueError. The push (server) and pull (client) sides share these
    rules verbatim, so a preset the server accepts can always be pulled."""
    if (
        not path
        or path.startswith("/")
        or "\\" in path
        # `:` covers Windows drive letters and is invalid on Windows targets.
        or ":" in path
        or any(part in ("", ".", "..") for part in path.split("/"))
    ):
        raise ValueError(f"Invalid preset file path {path!r}: must be a relative POSIX path")
    if path in _RESERVED_PRESET_FILE_PATHS:
        raise ValueError(f"Invalid preset file path {path!r}: the name is reserved")


def validate_preset_file_paths(paths: Sequence[str]) -> None:
    """Raises ValueError: per-path rules, duplicates, and file/directory prefix
    conflicts (`a` and `a/b` cannot both materialize on one filesystem)."""
    seen = set()
    directories = set()
    for path in paths:
        validate_preset_file_path(path)
        if path in seen:
            raise ValueError(f"Duplicate preset file path {path!r}")
        seen.add(path)
        parts = path.split("/")
        for index in range(1, len(parts)):
            directories.add("/".join(parts[:index]))
    conflicts = seen & directories
    if conflicts:
        raise ValueError(
            f"PortablePreset file path {sorted(conflicts)[0]!r} is both a file and a directory"
        )


class PresetSpec(CoreModel):
    """A preset with its files, as `RunSpec` carries a configuration with its
    file archives."""

    preset: PortablePreset
    file_archives: Annotated[
        List[FileArchiveMapping],
        Field(
            description=(
                "The files referenced by the preset service's `files`, as uploaded file"
                " archives, keyed by their path in the container exactly as `RunSpec`"
                " carries them"
            )
        ),
    ] = []


def validate_preset_spec_files(spec: PresetSpec) -> None:
    """Raises ValueError. The single owner of the file rules: push (server and
    client) and pull all call this, so what one side accepts the other can
    always materialize."""
    # `local_path` is what pull writes to disk, so it carries the rules. The
    # archives are keyed by the container path, as they are for a run, and only
    # have to line up with the service's files.
    local_paths = [mapping.local_path for mapping in spec.preset.service.files]
    validate_preset_file_paths(sorted(set(local_paths)))
    referenced_paths = {mapping.path for mapping in spec.preset.service.files}
    pushed_paths = [mapping.path for mapping in spec.file_archives]
    duplicate_paths = {path for path in pushed_paths if pushed_paths.count(path) > 1}
    if duplicate_paths:
        raise ValueError(f"Duplicate pushed files: {sorted(duplicate_paths)}")
    missing_paths = referenced_paths - set(pushed_paths)
    if missing_paths:
        raise ValueError(
            f"Files referenced by the preset are missing from the push: {sorted(missing_paths)}"
        )
    unreferenced_paths = set(pushed_paths) - referenced_paths
    if unreferenced_paths:
        raise ValueError(
            f"Pushed files are not referenced by the preset: {sorted(unreferenced_paths)}"
        )


def validate_preset_spec_limits(spec: PresetSpec) -> None:
    """Raises ValueError. Both sides measure the same object, so a spec the
    client accepts is never rejected by the server for size."""
    if len(spec.model_dump_json().encode("utf-8")) > MAX_PRESET_SPEC_SIZE:
        raise ValueError(f"PortablePreset spec exceeds the {MAX_PRESET_SPEC_SIZE}-byte limit")
    if len(spec.file_archives) > MAX_PRESET_FILES:
        raise ValueError(f"PortablePreset has more than {MAX_PRESET_FILES} files")


# Creation constraints


class PresetConstraints(CoreModel):
    """The effective constraints for preset creation, saved as `constraints.json`
    in the agent workspace. Field semantics are documented in the agent system prompt."""

    run_name_prefix: str
    model: PresetModelSpec
    min_context_length: PositiveInt
    max_ttft: PositiveInt
    trials_num: PositiveInt
    concurrency: PositiveInt
    baseline: bool
    fleets: Annotated[list[str], Field(min_length=1)]
    env: list[str]


class PresetRandomConstraints(PresetConstraints):
    """Constraints for the synthetic `random` dataset, which the request shape defines."""

    input_tokens: PositiveInt
    output_tokens: Annotated[int, Field(ge=2)]
    shared_prefix_tokens: Annotated[int, Field(ge=0)]


class PresetDatasetConstraints(PresetConstraints):
    """Constraints for a named dataset, which defines its own request shape."""

    dataset: str


def _validate_model(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Preset model {field} must be a non-empty string")
    return value
