import uuid
from typing import Optional

from pydantic import root_validator

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
    base: Optional[str] = None
    model: Optional[str] = None
    failure_summary: Optional[str] = None

    @root_validator
    def _validate_report(cls, values: dict) -> dict:
        success = values.get("success")
        if success:
            if values.get("run_id") is None:
                raise ValueError("successful agent report must include run_id")
            if not values.get("service_yaml"):
                raise ValueError("successful agent report must include service_yaml")
            if not values.get("base") or not values["base"].strip():
                raise ValueError("successful agent report must include base")
            if not values.get("model") or not values["model"].strip():
                raise ValueError("successful agent report must include model")
        else:
            if not values.get("failure_summary"):
                raise ValueError("failed agent report must include failure_summary")
        return values
