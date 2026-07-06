import json
import uuid
from asyncio import StreamReader
from datetime import datetime, timezone

import pytest
import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.server.services.endpoints.agent.claude as claude_module
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.endpoints import EndpointConfiguration, EndpointStatus
from dstack._internal.core.models.envs import Env
from dstack._internal.core.models.profiles import SpotPolicy
from dstack._internal.server import settings
from dstack._internal.server.models import (
    EndpointAgentAttemptModel,
    EndpointAgentAttemptStatus,
    EndpointModel,
)
from dstack._internal.server.services.endpoints.agent.claude import (
    ClaudeAgentService,
    _AgentRunnerResult,
    _AgentWorkspace,
    _build_claude_command,
    _read_agent_stdout,
    _run_agent_in_subprocess,
    _write_trace_record,
    get_claude_agent_unavailable_reason,
)
from dstack._internal.server.services.endpoints.agent.report import AgentFinalReport
from dstack._internal.server.testing.common import create_project, create_user


async def _create_endpoint_model(
    session: AsyncSession,
    max_agent_budget: float | None = None,
    max_price: float | None = None,
    spot_policy: SpotPolicy | None = None,
    backends: list[BackendType] | None = None,
    fleets: list[str] | None = None,
) -> EndpointModel:
    user = await create_user(session=session, name="admin", token="user-token")
    project = await create_project(session=session, owner=user, name="main")
    configuration = EndpointConfiguration(
        name="qwen-endpoint",
        model="Qwen/Qwen3-0.6B",
        env=Env.parse_obj({"HF_TOKEN": "hf-secret"}),
        max_agent_budget=max_agent_budget,
        max_price=max_price,
        spot_policy=spot_policy,
        backends=backends,
        fleets=fleets,
    )
    endpoint_model = EndpointModel(
        id=uuid.uuid4(),
        name=configuration.name,
        project=project,
        user=user,
        status=EndpointStatus.PROVISIONING,
        provisioning_method="agent",
        configuration=configuration.json(),
        created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        last_processed_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
    )
    session.add(endpoint_model)
    await session.commit()
    return endpoint_model


def _configure_fake_claude(tmp_path, monkeypatch: pytest.MonkeyPatch) -> str:
    claude_path = tmp_path / "claude"
    claude_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    claude_path.chmod(0o755)
    monkeypatch.setattr(settings, "AGENT_CLAUDE_PATH", str(claude_path))
    return str(claude_path)


class TestClaudeAgentService:
    @pytest.mark.asyncio
    async def test_default_runner_starts_agent_detached(
        self,
        session: AsyncSession,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "AGENT_ANTHROPIC_API_KEY", "agent-secret")
        _configure_fake_claude(tmp_path, monkeypatch)
        monkeypatch.setattr(settings, "SERVER_URL", "http://127.0.0.1:8000")
        started = {}

        def start_agent(workspace, request):
            started["workspace"] = workspace
            started["request"] = request
            return 12345

        monkeypatch.setattr(claude_module, "_start_agent_subprocess_detached", start_agent)
        endpoint_model = await _create_endpoint_model(session, max_agent_budget=1.5)
        service = ClaudeAgentService(workspace_base_dir=tmp_path)

        result = await service.provision_endpoint(endpoint_model, pipeline_hinter=None)

        assert result.in_progress is True
        assert result.error is None
        attempt_root = tmp_path / str(endpoint_model.id) / "1"
        assert started["workspace"].root_dir == attempt_root
        assert started["request"]["cwd"] == str(attempt_root / "workspace")
        assert started["request"]["options"]["max_budget"] == 1.5
        res = await session.execute(
            select(EndpointAgentAttemptModel).where(
                EndpointAgentAttemptModel.endpoint_id == endpoint_model.id
            )
        )
        attempt = res.scalar_one()
        assert attempt.attempt_num == 1
        assert attempt.status == EndpointAgentAttemptStatus.RUNNING
        assert attempt.pid == 12345
        assert attempt.workspace_path == str(attempt_root)

    @pytest.mark.asyncio
    async def test_invokes_agent_with_isolated_dstack_cli_context(
        self,
        session: AsyncSession,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "AGENT_ANTHROPIC_API_KEY", "agent-secret")
        claude_path = _configure_fake_claude(tmp_path, monkeypatch)
        monkeypatch.setattr(settings, "AGENT_ANTHROPIC_MODEL", "test-claude-model")
        monkeypatch.setattr(settings, "AGENT_ANTHROPIC_MAX_BUDGET", 3.0)
        monkeypatch.setattr(settings, "SERVER_URL", "http://127.0.0.1:8000")
        monkeypatch.setenv("DATABASE_URL", "must-not-leak")
        captured = {}
        run_id = uuid.uuid4()

        async def runner(workspace, request):
            captured["workspace"] = workspace
            captured["request"] = request
            return _AgentRunnerResult(
                report=AgentFinalReport(
                    success=True,
                    run_id=run_id,
                    run_name="qwen-agent-candidate",
                    service_yaml="type: service\nname: qwen-agent-candidate\n",
                    verification_summary="Agent verified chat completions.",
                )
            )

        endpoint_model = await _create_endpoint_model(session, max_agent_budget=1.5)
        service = ClaudeAgentService(runner=runner, workspace_base_dir=tmp_path)

        result = await service.provision_endpoint(endpoint_model, pipeline_hinter=None)

        assert result.error is None
        assert result.run_id == run_id
        assert result.run_name == "qwen-agent-candidate"
        assert result.final_report is not None
        assert result.final_report.verification_summary == "Agent verified chat completions."
        assert (
            "successful final report must include the verified service run `run_id`"
            in captured["request"]["prompt"]
        )
        attempt_root = tmp_path / str(endpoint_model.id) / "1"
        assert captured["request"]["cwd"] == str(attempt_root / "workspace")
        env = captured["request"]["env"]
        assert env["ANTHROPIC_API_KEY"] == "agent-secret"
        assert env["HOME"] == str(attempt_root / "home")
        assert env["DSTACK_PROJECT"] == "main"
        assert env["HF_TOKEN"] == "hf-secret"
        assert "DATABASE_URL" not in env
        assert captured["request"]["options"]["model"] == "test-claude-model"
        assert captured["request"]["options"]["max_budget"] == 1.5
        assert "StructuredOutput" in captured["request"]["options"]["tools"]
        assert "Edit" in captured["request"]["options"]["allowed_tools"]
        assert "StructuredOutput" in captured["request"]["options"]["allowed_tools"]
        schema_text = json.dumps(captured["request"]["options"]["json_schema"])
        assert '"title"' not in schema_text
        assert '"format"' not in schema_text
        command = _build_claude_command(captured["request"])
        assert command[0] == claude_path
        assert command[command.index("--tools") + 1] == captured["request"]["options"]["tools"]
        assert "--permission-mode" in command
        assert command[command.index("--permission-mode") + 1] == "bypassPermissions"
        assert "--max-budget-usd" in command
        assert command[command.index("--max-budget-usd") + 1] == "1.5"
        config = yaml.safe_load((attempt_root / "home" / ".dstack" / "config.yml").read_text())
        assert config == {
            "projects": [
                {
                    "name": "main",
                    "url": "http://127.0.0.1:8000",
                    "token": "user-token",
                    "default": True,
                }
            ],
        }
        work_dir = attempt_root / "workspace"
        state = json.loads((work_dir / "agent_state.json").read_text())
        assert state["endpoint_name"] == "qwen-endpoint"
        assert state["model"] == "Qwen/Qwen3-0.6B"
        assert state["phase"] == "success"
        assert state["max_agent_budget"] == 1.5
        assert (work_dir / "sources.jsonl").exists()
        assert (work_dir / "candidates.jsonl").exists()
        assert (work_dir / "commands.jsonl").exists()
        assert (work_dir / "progress.jsonl").exists()
        assert (work_dir / "hardware_reasoning.md").exists()
        assert (work_dir / ".claude" / "skills" / "dstack" / "SKILL.md").exists()
        assert (work_dir / ".claude" / "skills" / "dstack-prototyping" / "SKILL.md").exists()
        final_report = json.loads((work_dir / "final_report.json").read_text())
        assert final_report["success"] is True
        assert final_report["run_name"] == "qwen-agent-candidate"

    @pytest.mark.asyncio
    async def test_includes_endpoint_profile_constraints_in_prompt(
        self,
        session: AsyncSession,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "AGENT_ANTHROPIC_API_KEY", "agent-secret")
        _configure_fake_claude(tmp_path, monkeypatch)
        captured = {}

        async def runner(workspace, request):
            captured["request"] = request
            return _AgentRunnerResult(
                report=AgentFinalReport(
                    success=True,
                    run_id=uuid.uuid4(),
                    run_name="qwen-agent-candidate",
                    service_yaml="type: service\nname: qwen-agent-candidate\n",
                    verification_summary="Agent verified chat completions.",
                )
            )

        endpoint_model = await _create_endpoint_model(
            session,
            max_price=0.3,
            spot_policy=SpotPolicy.ONDEMAND,
        )
        service = ClaudeAgentService(runner=runner, workspace_base_dir=tmp_path)

        result = await service.provision_endpoint(endpoint_model, pipeline_hinter=None)

        assert result.error is None
        prompt = captured["request"]["prompt"]
        assert "- max_price: 0.3" in prompt
        assert "- spot_policy: on-demand" in prompt
        assert "--max-price 0.3 --on-demand" in prompt
        assert "--availability-zone" not in prompt
        assert "--instance " not in prompt

    @pytest.mark.asyncio
    async def test_prompt_points_to_bundled_skills_and_endpoint_contract(
        self,
        session: AsyncSession,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "AGENT_ANTHROPIC_API_KEY", "agent-secret")
        _configure_fake_claude(tmp_path, monkeypatch)
        captured = {}

        async def runner(workspace, request):
            captured["request"] = request
            return _AgentRunnerResult(
                report=AgentFinalReport(
                    success=True,
                    run_id=uuid.uuid4(),
                    run_name="qwen-agent-candidate",
                    service_yaml="type: service\nname: qwen-agent-candidate\n",
                    verification_summary="Agent verified chat completions.",
                )
            )

        endpoint_model = await _create_endpoint_model(
            session,
            max_price=0.5,
            spot_policy=SpotPolicy.ONDEMAND,
            backends=[BackendType.RUNPOD],
            fleets=["endpoint-e2e-runpod"],
        )
        service = ClaudeAgentService(runner=runner, workspace_base_dir=tmp_path)

        result = await service.provision_endpoint(endpoint_model, pipeline_hinter=None)

        assert result.error is None
        prompt = captured["request"]["prompt"]
        assert "Load and follow `/dstack`" in prompt
        assert "Load and follow `/dstack-prototyping`" in prompt
        assert "Bundled Claude Code skills are installed in `.claude/skills`" in prompt
        assert "Do not call hidden server APIs" in prompt
        assert "real model API request" in prompt
        assert "dstack-development" not in prompt
        assert "progress.jsonl" in prompt
        assert (
            "Do not write YAML, command output, long tables, raw traces, or secrets to "
            "`progress.jsonl`" in prompt
        )
        assert (
            "Record each dev environment, task, or service candidate in `candidates.jsonl`"
            in prompt
        )
        assert "verification.json" in prompt
        assert "service run name must not equal the endpoint name `qwen-endpoint`" in prompt
        assert "prefer `qwen-endpoint-1`, `qwen-endpoint-2`, etc." in prompt
        assert "Make each service YAML self-contained" in prompt
        assert "Do not wait only for log text" in prompt
        assert "Use normal service logs first" in prompt
        assert "- backends: runpod" in prompt
        assert (
            "- Reuse these CLI flags where applicable: --max-price 0.5 --on-demand --backend runpod --fleet endpoint-e2e-runpod"
            in prompt
        )
        assert "RUNPOD" not in prompt
        work_dir = tmp_path / str(endpoint_model.id) / "1" / "workspace"
        prototyping_skill = (
            work_dir / ".claude" / "skills" / "dstack-prototyping" / "SKILL.md"
        ).read_text()
        assert "Load `/dstack` first" in prototyping_skill
        assert "Do not repeat or override `/dstack` command syntax here" in prototyping_skill
        assert "Start with vLLM and SGLang" in prototyping_skill
        assert "Use a dev environment when an interactive shell can answer" in prototyping_skill
        assert "Never collapse tested hardware back into minimum requirements" in prototyping_skill
        assert "Do not treat `running`, a passed service probe, or clean logs" in prototyping_skill
        assert (
            "Retrying the same YAML after the same error is not prototyping" in prototyping_skill
        )
        assert "do not name a candidate service exactly like the endpoint" in prototyping_skill
        assert "Do not use `:latest` for a final serving image" in prototyping_skill
        assert "poll run JSON and stop waiting on terminal states" in prototyping_skill
        assert "Use normal logs before diagnostic logs" in prototyping_skill
        assert "include applicable backend, fleet, price, spot" in prototyping_skill
        assert "https://recipes.vllm.ai/models.json" in prototyping_skill
        assert (
            "https://www.lmsys.org/blog/2026-07-02-agent-assisted-sglang-development"
            in prototyping_skill
        )
        assert "dstack-development" not in prototyping_skill

    @pytest.mark.asyncio
    async def test_uses_server_default_agent_budget_when_endpoint_does_not_set_one(
        self,
        session: AsyncSession,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "AGENT_ANTHROPIC_API_KEY", "agent-secret")
        _configure_fake_claude(tmp_path, monkeypatch)
        monkeypatch.setattr(settings, "AGENT_ANTHROPIC_MAX_BUDGET", 4.0)
        captured = {}

        async def runner(workspace, request):
            captured["request"] = request
            return _AgentRunnerResult(
                report=AgentFinalReport(
                    success=True,
                    run_id=uuid.uuid4(),
                    run_name="qwen-agent-candidate",
                    service_yaml="type: service\nname: qwen-agent-candidate\n",
                    verification_summary="Agent verified chat completions.",
                )
            )

        endpoint_model = await _create_endpoint_model(session)
        service = ClaudeAgentService(runner=runner, workspace_base_dir=tmp_path)

        result = await service.provision_endpoint(endpoint_model, pipeline_hinter=None)

        assert result.error is None
        assert captured["request"]["options"]["max_budget"] == 4.0

    @pytest.mark.asyncio
    async def test_reuses_existing_final_report_without_invoking_runner(
        self,
        session: AsyncSession,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "AGENT_ANTHROPIC_API_KEY", "agent-secret")
        _configure_fake_claude(tmp_path, monkeypatch)
        endpoint_model = await _create_endpoint_model(session)
        work_dir = tmp_path / str(endpoint_model.id) / "workspace"
        work_dir.mkdir(parents=True)
        run_id = uuid.uuid4()
        (work_dir / "final_report.json").write_text(
            json.dumps(
                {
                    "success": True,
                    "run_id": str(run_id),
                    "run_name": "qwen-agent-candidate",
                    "service_yaml": "type: service\nname: qwen-agent-candidate\n",
                    "verification_summary": "Verified before restart.",
                }
            ),
            encoding="utf-8",
        )

        def start_agent(workspace, request):
            raise AssertionError("agent process must not be started")

        monkeypatch.setattr(claude_module, "_start_agent_subprocess_detached", start_agent)
        service = ClaudeAgentService(workspace_base_dir=tmp_path)

        result = await service.provision_endpoint(endpoint_model, pipeline_hinter=None)

        assert result.error is None
        assert result.run_id == run_id
        assert result.run_name == "qwen-agent-candidate"
        assert result.final_report is not None
        assert result.final_report.verification_summary == "Verified before restart."

    @pytest.mark.asyncio
    async def test_waits_for_claude_result_after_final_report_while_process_runs(
        self,
        session: AsyncSession,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "AGENT_ANTHROPIC_API_KEY", "agent-secret")
        _configure_fake_claude(tmp_path, monkeypatch)
        monkeypatch.setattr(
            claude_module,
            "_get_running_agent_process_pid",
            lambda workspace, attempt=None: 123,
        )
        endpoint_model = await _create_endpoint_model(session)
        work_dir = tmp_path / str(endpoint_model.id) / "workspace"
        work_dir.mkdir(parents=True)
        (work_dir / "final_report.json").write_text(
            json.dumps(
                {
                    "success": True,
                    "run_id": str(uuid.uuid4()),
                    "run_name": "qwen-agent-candidate",
                    "service_yaml": "type: service\nname: qwen-agent-candidate\n",
                    "verification_summary": "Verified before Claude exited.",
                }
            ),
            encoding="utf-8",
        )

        service = ClaudeAgentService(workspace_base_dir=tmp_path)

        result = await service.provision_endpoint(endpoint_model, pipeline_hinter=None)

        assert result.in_progress is True
        assert result.final_report is None

    @pytest.mark.asyncio
    async def test_reconciles_claude_cost_from_result_stream(
        self,
        session: AsyncSession,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "AGENT_ANTHROPIC_API_KEY", "agent-secret")
        _configure_fake_claude(tmp_path, monkeypatch)
        endpoint_model = await _create_endpoint_model(session)
        work_dir = tmp_path / str(endpoint_model.id) / "workspace"
        work_dir.mkdir(parents=True)
        run_id = uuid.uuid4()
        (work_dir / "final_report.json").write_text(
            json.dumps(
                {
                    "success": True,
                    "run_id": str(run_id),
                    "run_name": "qwen-agent-candidate",
                    "service_yaml": "type: service\nname: qwen-agent-candidate\n",
                    "verification_summary": "Verified before restart.",
                }
            ),
            encoding="utf-8",
        )
        (work_dir / "agent_stdout.jsonl").write_text(
            json.dumps(
                {
                    "type": "result",
                    "is_error": False,
                    "total_cost_usd": 0.42,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        service = ClaudeAgentService(workspace_base_dir=tmp_path)

        result = await service.provision_endpoint(endpoint_model, pipeline_hinter=None)

        assert result.error is None
        assert result.run_id == run_id
        res = await session.execute(
            select(EndpointAgentAttemptModel).where(
                EndpointAgentAttemptModel.endpoint_id == endpoint_model.id
            )
        )
        attempt = res.scalar_one()
        assert attempt.status == EndpointAgentAttemptStatus.SUCCEEDED
        assert attempt.spent_agent_budget == 0.42

    @pytest.mark.asyncio
    async def test_returns_in_progress_when_agent_process_is_still_running(
        self,
        session: AsyncSession,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "AGENT_ANTHROPIC_API_KEY", "agent-secret")
        _configure_fake_claude(tmp_path, monkeypatch)
        monkeypatch.setattr(
            claude_module,
            "_get_running_agent_process_pid",
            lambda workspace, attempt=None: 123,
        )
        endpoint_model = await _create_endpoint_model(session)

        def start_agent(workspace, request):
            raise AssertionError("agent process must not be started")

        monkeypatch.setattr(claude_module, "_start_agent_subprocess_detached", start_agent)
        service = ClaudeAgentService(workspace_base_dir=tmp_path)

        result = await service.provision_endpoint(endpoint_model, pipeline_hinter=None)

        assert result.in_progress is True
        assert result.error is None
        assert result.final_report is None

    @pytest.mark.asyncio
    async def test_writes_redacted_trace_in_debug_mode(
        self,
        session: AsyncSession,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "AGENT_ANTHROPIC_API_KEY", "agent-secret")
        _configure_fake_claude(tmp_path, monkeypatch)
        monkeypatch.setattr(settings, "LOG_LEVEL", "DEBUG")
        run_id = uuid.uuid4()

        async def runner(workspace, request):
            _write_trace_record(
                workspace,
                {"type": "FakeMessage", "text": "hf-secret agent-secret"},
            )
            return _AgentRunnerResult(
                report=AgentFinalReport(
                    success=True,
                    run_id=run_id,
                    run_name="qwen-agent-candidate",
                    service_yaml="token: hf-secret\n",
                    verification_summary="Agent verified with agent-secret.",
                )
            )

        endpoint_model = await _create_endpoint_model(session)
        service = ClaudeAgentService(runner=runner, workspace_base_dir=tmp_path)

        result = await service.provision_endpoint(endpoint_model, pipeline_hinter=None)

        assert result.error is None
        trace_path = tmp_path / str(endpoint_model.id) / "1" / "trace.jsonl"
        trace = trace_path.read_text()
        assert "agent-secret" not in trace
        assert "hf-secret" not in trace
        assert "[redacted]" in trace
        event = json.loads(trace.splitlines()[0])
        assert event["type"] == "FakeMessage"

    @pytest.mark.asyncio
    async def test_returns_error_when_sdk_fails_before_report(
        self,
        session: AsyncSession,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "AGENT_ANTHROPIC_API_KEY", "agent-secret")
        _configure_fake_claude(tmp_path, monkeypatch)

        async def runner(workspace, request):
            return _AgentRunnerResult(
                error="Server agent failed before returning a verification report: bad key"
            )

        endpoint_model = await _create_endpoint_model(session)
        service = ClaudeAgentService(runner=runner, workspace_base_dir=tmp_path)

        result = await service.provision_endpoint(endpoint_model, pipeline_hinter=None)

        assert (
            result.error == "Server agent failed before returning a verification report: bad key"
        )
        assert result.final_report is None
        work_dir = tmp_path / str(endpoint_model.id) / "1" / "workspace"
        state = json.loads((work_dir / "agent_state.json").read_text())
        assert state["phase"] == "failure"
        agent_error = json.loads((work_dir / "agent_error.json").read_text())
        assert agent_error["success"] is False
        assert agent_error["failure_summary"] == (
            "Server agent failed before returning a verification report: bad key"
        )

    def test_returns_error_when_configured_claude_path_is_not_executable(
        self,
        tmp_path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(settings, "AGENT_ANTHROPIC_API_KEY", "agent-secret")
        monkeypatch.setattr(settings, "AGENT_CLAUDE_PATH", str(tmp_path / "missing-claude"))

        assert get_claude_agent_unavailable_reason() == (
            "DSTACK_AGENT_CLAUDE_PATH does not resolve to an executable: "
            f"{tmp_path / 'missing-claude'}"
        )

    def test_returns_error_when_agent_key_is_blank(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "AGENT_ANTHROPIC_API_KEY", "")

        assert get_claude_agent_unavailable_reason() == (
            "DSTACK_AGENT_ANTHROPIC_API_KEY is not set."
        )

    def test_falls_back_to_claude_in_path(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "AGENT_CLAUDE_PATH", None)
        monkeypatch.setattr(settings, "AGENT_ANTHROPIC_API_KEY", "agent-secret")
        monkeypatch.setattr(
            claude_module.shutil,
            "which",
            lambda name: "/usr/local/bin/claude" if name == "claude" else None,
        )

        command = _build_claude_command(
            {
                "prompt": "prompt",
                "options": {
                    "allowed_tools": "Bash",
                    "disallowed_tools": "",
                    "model": "test-model",
                    "max_turns": 1,
                    "max_budget": None,
                    "json_schema": {},
                },
            }
        )

        assert get_claude_agent_unavailable_reason() is None
        assert command[0] == "/usr/local/bin/claude"

    @pytest.mark.asyncio
    async def test_reads_claude_stream_incrementally(self, tmp_path):
        reader = StreamReader()
        workspace = _AgentWorkspace(
            root_dir=tmp_path,
            home_dir=tmp_path / "home",
            work_dir=tmp_path / "work",
            trace_path=tmp_path / "trace.jsonl",
            env={},
            redacted_values=["secret"],
            endpoint_name="qwen-endpoint",
            model="Qwen/Qwen3-0.6B",
            max_agent_budget=None,
        )
        report = {
            "success": True,
            "run_id": str(uuid.uuid4()),
            "run_name": "qwen-agent-candidate",
            "service_yaml": "env: secret\n",
            "verification_summary": "verified secret",
        }
        reader.feed_data(
            json.dumps({"type": "assistant", "message": {"content": "working"}}).encode() + b"\n"
        )
        reader.feed_data(
            json.dumps({"type": "result", "result": json.dumps(report)}).encode() + b"\n"
        )
        reader.feed_eof()

        output = await _read_agent_stdout(reader, workspace)

        assert output.report_data == report
        trace = (tmp_path / "trace.jsonl").read_text()
        assert "secret" not in trace
        assert "[redacted]" in trace

    @pytest.mark.asyncio
    async def test_records_commands_without_copying_claude_stream_to_endpoint_logs(self, tmp_path):
        class FakeLogWriter:
            def __init__(self):
                self.messages = []

            async def write(self, message):
                self.messages.append(message)

            async def flush(self):
                pass

        reader = StreamReader()
        log_writer = FakeLogWriter()
        workspace = _AgentWorkspace(
            root_dir=tmp_path,
            home_dir=tmp_path / "home",
            work_dir=tmp_path / "work",
            trace_path=None,
            env={},
            redacted_values=["secret"],
            endpoint_name="qwen-endpoint",
            model="Qwen/Qwen3-0.6B",
            max_agent_budget=None,
            log_writer=log_writer,
        )
        reader.feed_data(
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "tool-1",
                                "name": "Bash",
                                "input": {
                                    "description": "List offers",
                                    "command": "dstack offer --gpu 1 --max-price 0.3",
                                },
                            }
                        ]
                    },
                }
            ).encode()
            + b"\n"
        )
        reader.feed_data(
            json.dumps(
                {
                    "type": "user",
                    "message": {
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "tool-1",
                                "content": "No offers secret",
                                "is_error": False,
                            }
                        ]
                    },
                }
            ).encode()
            + b"\n"
        )
        reader.feed_eof()

        await _read_agent_stdout(reader, workspace)

        assert log_writer.messages == []
        command_records = [
            json.loads(line)
            for line in (tmp_path / "work" / "commands.jsonl").read_text().splitlines()
        ]
        assert command_records[0]["event"] == "tool_use"
        assert command_records[0]["command"] == "dstack offer --gpu 1 --max-price 0.3"
        assert command_records[1]["event"] == "tool_result"
        assert command_records[1]["tool_use_id"] == "tool-1"
        output = (tmp_path / "work" / command_records[1]["output_path"]).read_text()
        assert output == "No offers [redacted]"

    @pytest.mark.asyncio
    async def test_stores_large_tool_outputs_without_endpoint_log_preview(self, tmp_path):
        class FakeLogWriter:
            def __init__(self):
                self.messages = []

            async def write(self, message):
                self.messages.append(message)

            async def flush(self):
                pass

        reader = StreamReader()
        log_writer = FakeLogWriter()
        workspace = _AgentWorkspace(
            root_dir=tmp_path,
            home_dir=tmp_path / "home",
            work_dir=tmp_path / "work",
            trace_path=None,
            env={},
            redacted_values=[],
            endpoint_name="qwen-endpoint",
            model="Qwen/Qwen3-0.6B",
            max_agent_budget=None,
            log_writer=log_writer,
        )
        long_output = "\n".join(f"offer {i:04d} gpu=A5000 price=0.27" for i in range(200))
        reader.feed_data(
            json.dumps(
                {
                    "type": "user",
                    "message": {
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "tool-1",
                                "content": long_output,
                                "is_error": False,
                            }
                        ]
                    },
                }
            ).encode()
            + b"\n"
        )
        reader.feed_eof()

        await _read_agent_stdout(reader, workspace)

        assert log_writer.messages == []
        command_records = [
            json.loads(line)
            for line in (tmp_path / "work" / "commands.jsonl").read_text().splitlines()
        ]
        output = (tmp_path / "work" / command_records[0]["output_path"]).read_text()
        assert output == long_output

    @pytest.mark.asyncio
    async def test_subprocess_streams_agent_progress_jsonl_to_endpoint_logs(
        self,
        tmp_path,
        monkeypatch,
    ):
        class FakeLogWriter:
            def __init__(self):
                self.messages = []

            async def write(self, message):
                self.messages.append(message)

            async def flush(self):
                pass

        claude_path = tmp_path / "claude"
        claude_path.write_text(
            """#!/bin/sh
printf '%s\\n' '{"phase":"research","message":"Checking recipes with secret"}' >> progress.jsonl
printf '%s\\n' '{"phase":"submit","message":"Submitted service candidate"}' >> progress.jsonl
cat > final_report.json <<'JSON'
{
  "success": true,
  "run_id": "6e578748-d597-4fde-a3a4-203587cad5a2",
  "run_name": "qwen-agent-candidate",
  "service_yaml": "type: service\\nname: qwen-agent-candidate\\n",
  "verification_summary": "Verified chat completions."
}
JSON
printf '%s\\n' '{"type":"result","is_error":false,"result":"done"}'
""",
            encoding="utf-8",
        )
        claude_path.chmod(0o755)
        monkeypatch.setattr(settings, "AGENT_CLAUDE_PATH", str(claude_path))
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        log_writer = FakeLogWriter()
        workspace = _AgentWorkspace(
            root_dir=tmp_path,
            home_dir=tmp_path / "home",
            work_dir=work_dir,
            trace_path=None,
            env={},
            redacted_values=["secret"],
            endpoint_name="qwen-endpoint",
            model="Qwen/Qwen3-0.6B",
            max_agent_budget=None,
            log_writer=log_writer,
        )
        request = {
            "prompt": "prompt",
            "env": {},
            "cwd": str(work_dir),
            "options": {
                "allowed_tools": "Bash",
                "disallowed_tools": "",
                "model": "test-model",
                "max_turns": 1,
                "max_budget": None,
                "json_schema": {},
            },
        }
        (work_dir / "progress.jsonl").write_text(
            '{"phase":"old","message":"Old progress must not replay"}\n',
            encoding="utf-8",
        )

        result = await _run_agent_in_subprocess(workspace, request)

        assert result.error is None
        assert log_writer.messages == [
            "research: Checking recipes with [redacted]",
            "submit: Submitted service candidate",
        ]

    @pytest.mark.asyncio
    async def test_subprocess_uses_final_report_artifact_when_stream_result_is_missing(
        self,
        tmp_path,
        monkeypatch,
    ):
        claude_path = tmp_path / "claude"
        claude_path.write_text(
            """#!/bin/sh
cat > final_report.json <<'JSON'
{
  "success": true,
  "run_id": "6e578748-d597-4fde-a3a4-203587cad5a2",
  "run_name": "qwen-agent-candidate",
  "service_yaml": "type: service\\nname: qwen-agent-candidate\\n",
  "verification_summary": "Verified chat completions over SSH."
}
JSON
printf '%s\\n' '{"type":"result","is_error":false,"result":"done"}'
""",
            encoding="utf-8",
        )
        claude_path.chmod(0o755)
        monkeypatch.setattr(settings, "AGENT_CLAUDE_PATH", str(claude_path))
        (tmp_path / "work").mkdir()
        workspace = _AgentWorkspace(
            root_dir=tmp_path,
            home_dir=tmp_path / "home",
            work_dir=tmp_path / "work",
            trace_path=None,
            env={},
            redacted_values=[],
            endpoint_name="qwen-endpoint",
            model="Qwen/Qwen3-0.6B",
            max_agent_budget=None,
        )
        request = {
            "prompt": "prompt",
            "env": {},
            "cwd": str(tmp_path / "work"),
            "options": {
                "allowed_tools": "Bash",
                "disallowed_tools": "",
                "model": "test-model",
                "max_turns": 1,
                "max_budget": None,
                "json_schema": {},
            },
        }

        result = await _run_agent_in_subprocess(workspace, request)

        assert result.error is None
        assert result.report is not None
        assert result.report.success is True
        assert result.report.run_name == "qwen-agent-candidate"
        assert result.report.verification_summary == "Verified chat completions over SSH."

    @pytest.mark.asyncio
    async def test_subprocess_no_report_error_does_not_include_stream_output(
        self,
        tmp_path,
        monkeypatch,
    ):
        claude_path = tmp_path / "claude"
        claude_path.write_text(
            "#!/bin/sh\n"
            'printf \'%s\\n\' \'{"type":"user","message":{"content":[{"type":"tool_result","content":"huge offer table","is_error":false}]}}\' >&2\n'
            "exit 143\n",
            encoding="utf-8",
        )
        claude_path.chmod(0o755)
        monkeypatch.setattr(settings, "AGENT_CLAUDE_PATH", str(claude_path))
        (tmp_path / "work").mkdir()
        workspace = _AgentWorkspace(
            root_dir=tmp_path,
            home_dir=tmp_path / "home",
            work_dir=tmp_path / "work",
            trace_path=None,
            env={},
            redacted_values=[],
            endpoint_name="qwen-endpoint",
            model="Qwen/Qwen3-0.6B",
            max_agent_budget=None,
        )
        request = {
            "prompt": "prompt",
            "env": {},
            "options": {
                "allowed_tools": "Bash",
                "disallowed_tools": "",
                "model": "test-model",
                "max_turns": 1,
                "max_budget": None,
                "json_schema": {},
            },
        }

        result = await _run_agent_in_subprocess(workspace, request)

        assert result.error == (
            "Server agent process exited without a verification report (return code 143)"
        )
        assert "huge offer table" not in result.error
