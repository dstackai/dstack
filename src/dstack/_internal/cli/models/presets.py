import re
from datetime import datetime
from typing import Annotated, Literal, Optional

from pydantic import (
    Field,
    PositiveFloat,
    PositiveInt,
    parse_obj_as,
    root_validator,
    validator,
)

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.profiles import ProfileParams
from dstack._internal.core.models.resources import CPUSpec, ResourcesSpec


class PresetBenchmarkWorkload(CoreModel):
    api: Literal["chat_completions", "completions"]
    num_requests: PositiveInt
    input_tokens: PositiveInt
    output_tokens: Annotated[int, Field(ge=2)]
    concurrency: PositiveInt


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
    ttft_ms: PresetBenchmarkLatency
    tpot_ms: PresetBenchmarkLatency


class PresetBenchmarkTarget(CoreModel):
    type: Literal["gateway", "server-proxy"]


class PresetBenchmarkClient(CoreModel):
    type: Literal["local"]


class PresetBenchmark(CoreModel):
    tool: str
    tool_version: str
    command: str
    workload: PresetBenchmarkWorkload
    metrics: PresetBenchmarkMetrics
    target: Optional[PresetBenchmarkTarget] = None
    client: Optional[PresetBenchmarkClient] = None

    @validator("tool", "tool_version", "command")
    def validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must be non-empty")
        return value

    @validator("command")
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

    @root_validator(skip_on_failure=True)
    def validate_metrics(cls, values: dict) -> dict:
        metrics = values.get("metrics")
        workload = values.get("workload")
        assert metrics is not None and workload is not None
        if metrics.failed_requests != 0:
            raise ValueError("benchmark must not include failed requests")
        if metrics.successful_requests != workload.num_requests:
            raise ValueError("benchmark request count must match workload.num_requests")
        return values


class PresetValidationReplica(CoreModel):
    resources: list[ResourcesSpec]
    """Exact resources for each running replica in this service replica group."""


class PresetValidation(CoreModel):
    replicas: list[PresetValidationReplica]
    """Ordered to match `ServiceConfiguration.replica_groups`."""
    benchmark: PresetBenchmark


class Preset(CoreModel):
    base: str
    """Base model used for local preset lookup."""
    id: str
    name: Optional[str] = None
    """Mutable human name; at most one preset or in-flight session holds it."""
    model: str
    """Exact repo/path loaded by the service command."""
    context_length: PositiveInt
    """Token context length this preset was verified to support."""
    created_at: datetime
    service: ServiceConfiguration
    validations: list[PresetValidation]

    @validator("base", "id", "model")
    def validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must be non-empty")
        return value

    @root_validator
    def validate_preset(cls, values: dict) -> dict:
        service = values.get("service")
        validations = values.get("validations")
        if service is None or validations is None:
            return values
        if service.model is None:
            raise ValueError("preset service must specify model")
        if any(group.resources is None for group in service.replica_groups):
            raise ValueError("preset service must specify resources")
        if service.name is not None or service.gateway is not None:
            raise ValueError("preset service must not specify name or gateway")
        if any(getattr(service, field) is not None for field in ProfileParams.__fields__):
            raise ValueError("preset service must not specify placement constraints")
        if not validations:
            raise ValueError("preset must include validation evidence")
        for validation in validations:
            if len(validation.replicas) != len(service.replica_groups):
                raise ValueError(
                    "preset validation replicas must match service replica group order"
                )
            if validation.benchmark.target is None or validation.benchmark.client is None:
                raise ValueError("preset benchmark must specify target and client")
            for replica_group in validation.replicas:
                if not replica_group.resources:
                    raise ValueError("preset validation replicas must specify resources")
                for resources in replica_group.resources:
                    _validate_exact_resources(resources)
        return values


class PresetListOutput(CoreModel):
    presets: list[Preset]


def _validate_exact_resources(resources: ResourcesSpec) -> None:
    cpu = parse_obj_as(CPUSpec, resources.cpu)
    if not _is_exact(cpu.count) or not _is_exact(resources.memory):
        raise ValueError("preset validation resources must be exact")
    if resources.disk is None or not _is_exact(resources.disk.size):
        raise ValueError("preset validation resources must be exact")
    gpu = resources.gpu
    if gpu is None or not _is_exact(gpu.count):
        raise ValueError("preset validation resources must be exact")
    if gpu.count.min == 0:
        return
    if gpu.name is None or len(gpu.name) != 1 or not _is_exact(gpu.memory):
        raise ValueError("preset validation resources must be exact")


def _is_exact(value) -> bool:
    return (
        value is not None
        and value.min is not None
        and value.max is not None
        and value.min == value.max
    )
