import uuid
from typing import Optional

from pydantic import PositiveInt, root_validator

from dstack._internal.core.models.common import CoreModel

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
    failure_summary: Optional[str] = None

    @root_validator
    def validate_report(cls, values: dict) -> dict:
        if values.get("success"):
            required = ("run_id", "run_name", "service_yaml", "base", "model", "context_length")
            missing = [field for field in required if values.get(field) in (None, "")]
            if missing:
                raise ValueError("successful agent report must include " + ", ".join(missing))
        elif not values.get("failure_summary"):
            raise ValueError("failed agent report must include failure_summary")
        return values
