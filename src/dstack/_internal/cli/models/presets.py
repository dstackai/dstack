import re
from datetime import datetime
from typing import Annotated, Literal, Optional, Union

from pydantic import (
    Field,
    PositiveFloat,
    PositiveInt,
    field_validator,
    model_validator,
)
from typing_extensions import Self

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.presets import PresetConfiguration
from dstack._internal.core.models.profiles import ProfileParams
from dstack._internal.core.models.resources import Range, ResourcesSpec

# The service name, the gateway, and the profile parameters are chosen by whoever
# runs `dstack apply` with the preset, so a preset never carries them.
PRESET_EXCLUDED_FIELDS = ("name", "gateway", *ProfileParams.model_fields)


class PresetWorkload(CoreModel):
    api: Literal["chat_completions", "completions"]
    dataset: str
    num_requests: PositiveInt
    input_tokens: PositiveInt
    output_tokens: Annotated[int, Field(ge=2)]
    concurrency: PositiveInt


class PresetRandomWorkload(PresetWorkload):
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
    replicas: list[ResourcesSpec]


class Preset(CoreModel):
    status: Literal["running", "interrupted", "failed", "verified"]
    id: str
    name: Optional[str] = None
    configuration: PresetConfiguration
    submitted_at: datetime


class VerifiedPreset(Preset):
    status: Literal["verified"] = "verified"
    base: Annotated[str, Field(min_length=1)]
    model: Annotated[str, Field(min_length=1)]
    # The largest context the service was verified to serve.
    context_length: PositiveInt
    # The session's `trials/<n>` that won verification and became this preset.
    best_trial: PositiveInt
    # The verified run's spec configuration, not the agent's files. The
    # validator below keeps `name`, `gateway`, and profile params unset (the
    # deployer's choices) and requires `model` and resources. Env keys the
    # user declared as passthroughs hold `EnvSentinel` references, not the
    # resolved secrets; other env values are stored as-is. `files` paths are
    # stored relative to the preset directory, absolute after load.
    service: ServiceConfiguration
    benchmark: PresetBenchmark
    # The hardware it was verified on: the actual resources of every running
    # replica, by service replica group.
    verified_on: list[PresetVerificationReplicaGroup]

    @model_validator(mode="after")
    def validate_preset(self) -> Self:
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


class PresetListOutput(CoreModel):
    presets: list[VerifiedPreset]


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
