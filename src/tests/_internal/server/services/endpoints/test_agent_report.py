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
                "run_name": "qwen-serving",
                "service_yaml": "type: service\nname: qwen-serving\n",
                "base": "Qwen/Qwen3-0.6B",
                "model": "Qwen/Qwen3-0.6B",
            }
        )

        assert report.run_id == run_id
        assert report.run_name == "qwen-serving"
        assert report.base == "Qwen/Qwen3-0.6B"
        assert report.model == "Qwen/Qwen3-0.6B"

    def test_rejects_success_without_run_id(self):
        with pytest.raises(ValidationError, match="run_id"):
            AgentFinalReport.parse_obj(
                {
                    "success": True,
                    "run_name": "qwen-serving",
                    "service_yaml": "type: service\nname: qwen-serving\n",
                    "base": "Qwen/Qwen3-0.6B",
                    "model": "Qwen/Qwen3-0.6B",
                }
            )

    def test_rejects_success_with_empty_base(self):
        with pytest.raises(ValidationError, match="base"):
            AgentFinalReport.parse_obj(
                {
                    "success": True,
                    "run_id": str(uuid.uuid4()),
                    "run_name": "qwen-serving",
                    "service_yaml": "type: service\nname: qwen-serving\n",
                    "base": "",
                    "model": "Qwen/Qwen3-0.6B",
                }
            )

    def test_rejects_success_with_empty_model(self):
        with pytest.raises(ValidationError, match="model"):
            AgentFinalReport.parse_obj(
                {
                    "success": True,
                    "run_id": str(uuid.uuid4()),
                    "run_name": "qwen-serving",
                    "service_yaml": "type: service\nname: qwen-serving\n",
                    "base": "Qwen/Qwen3-0.6B",
                    "model": "",
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
