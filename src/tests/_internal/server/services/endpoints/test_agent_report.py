import uuid

import pytest
from pydantic import ValidationError

from dstack._internal.server.services.endpoints.agent.report import AgentFinalReport


class TestAgentFinalReport:
    def test_accepts_success_report(self):
        run_id = uuid.uuid4()

        report = AgentFinalReport.parse_obj(
            {
                "success": True,
                "run_id": str(run_id),
                "service_yaml": "type: service\nname: qwen-serving\n",
                "recipe_sources": ["https://example.com/recipe"],
                "verification_summary": "Chat completion request returned 200.",
            }
        )

        assert report.run_id == run_id
        assert report.recipe_sources == ["https://example.com/recipe"]

    def test_rejects_success_without_verification_summary(self):
        with pytest.raises(ValidationError, match="verification_summary"):
            AgentFinalReport.parse_obj(
                {
                    "success": True,
                    "run_id": str(uuid.uuid4()),
                    "run_name": "qwen-serving",
                    "service_yaml": "type: service\nname: qwen-serving\n",
                }
            )

    def test_rejects_success_without_run_id(self):
        with pytest.raises(ValidationError, match="run_id"):
            AgentFinalReport.parse_obj(
                {
                    "success": True,
                    "run_name": "qwen-serving",
                    "service_yaml": "type: service\nname: qwen-serving\n",
                    "verification_summary": "Chat completion request returned 200.",
                }
            )

    def test_accepts_failure_report(self):
        report = AgentFinalReport.parse_obj(
            {
                "success": False,
                "failure_summary": "No deployable recipe matched the budget.",
            }
        )

        assert report.failure_summary == "No deployable recipe matched the budget."

    def test_rejects_failure_without_summary(self):
        with pytest.raises(ValidationError, match="failure_summary"):
            AgentFinalReport.parse_obj({"success": False})
