import uuid
from typing import Optional

from pydantic import Field, root_validator

from dstack._internal.core.models.common import CoreModel

AGENT_FINAL_REPORT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean"},
        "run_id": {"type": "string"},
        "run_name": {"type": "string"},
        "service_yaml": {"type": "string"},
        "recipe_sources": {"type": "array", "items": {"type": "string"}},
        "verification_summary": {"type": "string"},
        "failure_summary": {"type": "string"},
    },
    "required": ["success"],
    "additionalProperties": False,
}


class AgentFinalReport(CoreModel):
    # TODO: Keep this contract intentionally minimal until real agent runs show
    # which validation evidence is actually useful and reliable.
    success: bool
    run_id: Optional[uuid.UUID] = None
    run_name: Optional[str] = None
    service_yaml: Optional[str] = None
    recipe_sources: list[str] = Field(default_factory=list)
    verification_summary: Optional[str] = None
    failure_summary: Optional[str] = None

    @root_validator
    def _validate_report(cls, values: dict) -> dict:
        success = values.get("success")
        if success:
            if values.get("run_id") is None:
                raise ValueError("successful agent report must include run_id")
            if not values.get("service_yaml"):
                raise ValueError("successful agent report must include service_yaml")
            if not values.get("verification_summary"):
                raise ValueError("successful agent report must include verification_summary")
        else:
            if not values.get("failure_summary"):
                raise ValueError("failed agent report must include failure_summary")
        return values
