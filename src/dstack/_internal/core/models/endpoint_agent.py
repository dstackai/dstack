import uuid
from typing import Optional

from pydantic import PositiveInt, root_validator

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.endpoint_presets import EndpointBenchmark

_LATENCY_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "mean": {"type": "number", "minimum": 0},
        "p50": {"type": "number", "minimum": 0},
        "p99": {"type": "number", "minimum": 0},
    },
    "required": ["mean", "p50", "p99"],
    "additionalProperties": False,
}

_BENCHMARK_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "tool": {"type": "string", "minLength": 1},
        "tool_version": {"type": "string", "minLength": 1},
        "command": {"type": "string", "minLength": 1},
        "workload": {
            "type": "object",
            "properties": {
                "api": {
                    "type": "string",
                    "enum": ["chat_completions", "completions"],
                },
                "num_requests": {"type": "integer", "minimum": 1},
                "input_tokens": {"type": "integer", "minimum": 1},
                "output_tokens": {"type": "integer", "minimum": 2},
                "concurrency": {"type": "integer", "minimum": 1},
            },
            "required": [
                "api",
                "num_requests",
                "input_tokens",
                "output_tokens",
                "concurrency",
            ],
            "additionalProperties": False,
        },
        "metrics": {
            "type": "object",
            "properties": {
                "successful_requests": {"type": "integer", "minimum": 0},
                "failed_requests": {"type": "integer", "minimum": 0},
                "duration_seconds": {"type": "number", "exclusiveMinimum": 0},
                "total_input_tokens": {"type": "integer", "minimum": 0},
                "total_output_tokens": {"type": "integer", "minimum": 0},
                "ttft_ms": _LATENCY_JSON_SCHEMA,
                "tpot_ms": _LATENCY_JSON_SCHEMA,
            },
            "required": [
                "successful_requests",
                "failed_requests",
                "duration_seconds",
                "total_input_tokens",
                "total_output_tokens",
                "ttft_ms",
                "tpot_ms",
            ],
            "additionalProperties": False,
        },
    },
    "required": ["tool", "tool_version", "command", "workload", "metrics"],
    "additionalProperties": False,
}

AGENT_FINAL_REPORT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean"},
        "run_id": {"type": "string"},
        "run_name": {"type": "string"},
        "service_yaml": {"type": "string"},
        "base": {"type": "string"},
        "model": {"type": "string"},
        "context_length": {"type": "integer", "minimum": 1},
        "benchmark": _BENCHMARK_JSON_SCHEMA,
        "failure_summary": {"type": "string"},
    },
    "required": ["success"],
    "additionalProperties": False,
}


class AgentFinalReport(CoreModel):
    success: bool
    run_id: Optional[uuid.UUID] = None
    run_name: Optional[str] = None
    service_yaml: Optional[str] = None
    base: Optional[str] = None
    model: Optional[str] = None
    context_length: Optional[PositiveInt] = None
    benchmark: Optional[EndpointBenchmark] = None
    failure_summary: Optional[str] = None

    @root_validator
    def validate_report(cls, values: dict) -> dict:
        if values.get("success"):
            required = (
                "run_id",
                "run_name",
                "service_yaml",
                "base",
                "model",
                "context_length",
                "benchmark",
            )
            missing = [field for field in required if values.get(field) in (None, "")]
            if missing:
                raise ValueError("successful agent report must include " + ", ".join(missing))
        elif not values.get("failure_summary"):
            raise ValueError("failed agent report must include failure_summary")
        return values
