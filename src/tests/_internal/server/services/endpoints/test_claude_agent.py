import json
import signal
import stat
import subprocess
import uuid
from asyncio import StreamReader
from datetime import datetime, timezone
from pathlib import Path

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
    EndpointAgentSessionModel,
    EndpointAgentSessionStatus,
    EndpointModel,
)
from dstack._internal.server.services.endpoints.agent.claude import (
    ClaudeAgentService,
    _AgentRunnerResult,
    _AgentWorkspace,
    _build_claude_command,
    _load_submissions,
    _read_agent_stdout,
    _run_agent_in_subprocess,
    _write_trace_record,
    get_claude_agent_unavailable_reason,
)
from dstack._internal.server.services.endpoints.agent.report import AgentFinalReport
from dstack._internal.server.testing.common import (
    create_fleet,
    create_project,
    create_user,
)


async def _create_endpoint_model(
    session: AsyncSession,
    max_price: float | None = None,
    spot_policy: SpotPolicy | None = None,
    backends: list[BackendType] | None = None,
    fleets: list[str] | None = None,
    create_default_fleet: bool = True,
) -> EndpointModel:
    user = await create_user(session=session, name="admin", token="user-token")
    project = await create_project(session=session, owner=user, name="main")
    if create_default_fleet:
        await create_fleet(session=session, project=project)
    configuration = EndpointConfiguration(
        name="qwen-endpoint",
        model="Qwen/Qwen3-0.6B",
        env=Env.parse_obj({"HF_TOKEN": "hf-secret"}),
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
        written_logs = []

        def write_logs(**kwargs):
            written_logs.extend(log.message.decode().rstrip("\n") for log in kwargs["job_logs"])

        def start_agent(workspace, request):
            started["workspace"] = workspace
            started["request"] = request
            return 12345

        monkeypatch.setattr(claude_module.logs_services, "write_logs", write_logs)
        monkeypatch.setattr(claude_module, "_start_agent_subprocess_detached", start_agent)
        endpoint_model = await _create_endpoint_model(session)
        service = ClaudeAgentService(workspace_base_dir=tmp_path)

        result = await service.provision_endpoint(endpoint_model, pipeline_hinter=None)

        assert result.in_progress is True
        assert result.error is None
        session_root = tmp_path / str(endpoint_model.id) / "1"
        assert started["workspace"].root_dir == session_root
        assert started["request"]["cwd"] == str(session_root / "workspace")
        assert "max_budget" not in started["request"]["options"]
        res = await session.execute(
            select(EndpointAgentSessionModel).where(
                EndpointAgentSessionModel.endpoint_id == endpoint_model.id
            )
        )
        agent_session = res.scalar_one()
        assert agent_session.session_num == 1
        assert agent_session.status == EndpointAgentSessionStatus.RUNNING
        assert agent_session.pid == 12345
        assert agent_session.workspace_path == str(session_root)
        progress_path = session_root / "workspace" / "progress.jsonl"
        progress_text = progress_path.read_text()
        assert "Starting endpoint prototyping agent for Qwen/Qwen3-0.6B" in progress_text
        assert agent_session.progress_log_offset == progress_path.stat().st_size
        assert written_logs == [
            "Starting endpoint prototyping agent for Qwen/Qwen3-0.6B. "
            "Allowed fleets: test-fleet. The agent will inspect offers, choose a service "
            "recipe, deploy it, and verify the model API before the endpoint becomes active."
        ]

    @pytest.mark.asyncio
    async def test_restart_resumes_same_session_when_previous_process_exited(
        self,
        session: AsyncSession,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "AGENT_ANTHROPIC_API_KEY", "agent-secret")
        _configure_fake_claude(tmp_path, monkeypatch)
        monkeypatch.setattr(settings, "SERVER_URL", "http://127.0.0.1:8000")
        endpoint_model = await _create_endpoint_model(session)
        session_root = tmp_path / str(endpoint_model.id) / "1"
        work_dir = session_root / "workspace"
        work_dir.mkdir(parents=True)
        (work_dir / "submissions.jsonl").write_text(
            json.dumps(
                {
                    "name": "qwen-endpoint-1",
                    "type": "service",
                    "status": "submitted",
                    "run_id": str(uuid.uuid4()),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        agent_session = EndpointAgentSessionModel(
            endpoint_id=endpoint_model.id,
            session_num=1,
            status=EndpointAgentSessionStatus.RUNNING,
            workspace_path=str(session_root),
            pid=12345,
            process_host=claude_module._get_process_host(),
            progress_log_offset=0,
            stdout_log_offset=0,
            stderr_log_offset=0,
            created_at=endpoint_model.created_at,
            updated_at=endpoint_model.created_at,
        )
        session.add(agent_session)
        await session.commit()
        monkeypatch.setattr(claude_module, "_is_process_group_running", lambda pgid: False)
        started = {}

        def start_agent(workspace, request):
            started["workspace"] = workspace
            started["request"] = request
            return 23456

        monkeypatch.setattr(claude_module, "_start_agent_subprocess_detached", start_agent)
        service = ClaudeAgentService(workspace_base_dir=tmp_path)

        result = await service.provision_endpoint(endpoint_model, pipeline_hinter=None)

        assert result.in_progress is True
        assert result.error is None
        assert started["workspace"].root_dir == session_root
        assert "On startup or resume" in started["request"]["prompt"]
        assert "previous_sessions.md" not in started["request"]["prompt"]
        await session.refresh(agent_session)
        assert agent_session.session_num == 1
        assert agent_session.status == EndpointAgentSessionStatus.RUNNING
        assert agent_session.pid == 23456
        assert agent_session.workspace_path == str(session_root)

    @pytest.mark.asyncio
    async def test_new_endpoint_lifecycle_starts_new_session_without_previous_context(
        self,
        session: AsyncSession,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "AGENT_ANTHROPIC_API_KEY", "agent-secret")
        _configure_fake_claude(tmp_path, monkeypatch)
        endpoint_model = await _create_endpoint_model(session)
        previous_root = tmp_path / str(endpoint_model.id) / "1"
        previous_work_dir = previous_root / "workspace"
        previous_work_dir.mkdir(parents=True)
        previous_run_id = uuid.uuid4()
        (previous_work_dir / "final_report.json").write_text(
            json.dumps(
                {
                    "success": False,
                    "run_id": str(previous_run_id),
                    "run_name": "qwen-endpoint-1",
                    "service_yaml": "type: service\nname: qwen-endpoint-1\n",
                    "failure_summary": "Previous image required a newer driver.",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (previous_work_dir / "submissions.jsonl").write_text(
            json.dumps(
                {
                    "name": "qwen-endpoint-1",
                    "status": "failed",
                    "run_id": str(previous_run_id),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        previous_session = EndpointAgentSessionModel(
            endpoint_id=endpoint_model.id,
            session_num=1,
            status=EndpointAgentSessionStatus.FAILED,
            workspace_path=str(previous_root),
            progress_log_offset=0,
            stdout_log_offset=0,
            stderr_log_offset=0,
            status_message="Previous image required a newer driver.",
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
            updated_at=datetime(2023, 1, 2, 3, 5, tzinfo=timezone.utc),
            finished_at=datetime(2023, 1, 2, 3, 6, tzinfo=timezone.utc),
        )
        session.add(previous_session)
        endpoint_model.created_at = datetime(2023, 1, 3, 3, 4, tzinfo=timezone.utc)
        await session.commit()
        captured = {}

        async def runner(workspace, request):
            captured["workspace"] = workspace
            captured["request"] = request
            return _AgentRunnerResult(
                report=AgentFinalReport(
                    success=True,
                    run_id=uuid.uuid4(),
                    run_name="qwen-endpoint-1",
                    service_yaml="type: service\nname: qwen-endpoint-1\n",
                )
            )

        service = ClaudeAgentService(runner=runner, workspace_base_dir=tmp_path)

        result = await service.provision_endpoint(endpoint_model, pipeline_hinter=None)

        assert result.error is None
        assert captured["workspace"].root_dir == tmp_path / str(endpoint_model.id) / "2"
        prompt = captured["request"]["prompt"]
        assert "previous_sessions.md" not in prompt
        assert "Previous image required a newer driver." not in prompt
        assert not (
            tmp_path / str(endpoint_model.id) / "2" / "workspace" / "previous_sessions.md"
        ).exists()
        res = await session.execute(
            select(EndpointAgentSessionModel)
            .where(EndpointAgentSessionModel.endpoint_id == endpoint_model.id)
            .order_by(EndpointAgentSessionModel.session_num)
        )
        sessions = list(res.scalars().all())
        assert [agent_session.session_num for agent_session in sessions] == [1, 2]

    @pytest.mark.asyncio
    async def test_abort_endpoint_stops_agent_process_group(
        self,
        session: AsyncSession,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "SERVER_URL", "http://127.0.0.1:8000")
        endpoint_model = await _create_endpoint_model(session)
        session_root = tmp_path / str(endpoint_model.id) / "1"
        work_dir = session_root / "workspace"
        work_dir.mkdir(parents=True)
        process_state_path = work_dir / "agent_process.json"
        process_state_path.write_text(
            json.dumps(
                {
                    "pid": 12345,
                    "pgid": 12345,
                    "host": claude_module._get_process_host(),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        agent_session = EndpointAgentSessionModel(
            endpoint_id=endpoint_model.id,
            session_num=1,
            status=EndpointAgentSessionStatus.RUNNING,
            workspace_path=str(session_root),
            pid=12345,
            process_host=claude_module._get_process_host(),
            progress_log_offset=0,
            stdout_log_offset=0,
            stderr_log_offset=0,
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
            updated_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        session.add(agent_session)
        await session.commit()

        group_running = iter([True, False])
        signals = []

        monkeypatch.setattr(
            claude_module,
            "_is_process_group_running",
            lambda pgid: next(group_running),
        )
        monkeypatch.setattr(claude_module, "_AGENT_PROCESS_ABORT_GRACE_SECONDS", 0)
        monkeypatch.setattr(
            claude_module.os,
            "killpg",
            lambda pgid, sig: signals.append((pgid, sig)),
        )

        service = ClaudeAgentService(workspace_base_dir=tmp_path)

        aborted = await service.abort_endpoint(endpoint_model)

        assert aborted is True
        assert signals == [(12345, signal.SIGTERM)]
        assert not process_state_path.exists()
        await session.refresh(agent_session)
        assert agent_session.status == EndpointAgentSessionStatus.FAILED
        assert agent_session.status_message == "Endpoint stop requested"

    @pytest.mark.asyncio
    async def test_abort_endpoint_waits_for_agent_process_on_another_host(
        self,
        session: AsyncSession,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.setattr(settings, "SERVER_URL", "http://127.0.0.1:8000")
        endpoint_model = await _create_endpoint_model(session)
        session_root = tmp_path / str(endpoint_model.id) / "1"
        work_dir = session_root / "workspace"
        work_dir.mkdir(parents=True)
        process_state_path = work_dir / "agent_process.json"
        process_state_path.write_text(
            json.dumps({"pid": 12345, "pgid": 12345, "host": "other-host"}) + "\n",
            encoding="utf-8",
        )
        agent_session = EndpointAgentSessionModel(
            endpoint_id=endpoint_model.id,
            session_num=1,
            status=EndpointAgentSessionStatus.RUNNING,
            workspace_path=str(session_root),
            pid=12345,
            process_host="other-host",
            progress_log_offset=0,
            stdout_log_offset=0,
            stderr_log_offset=0,
            created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
            updated_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        )
        session.add(agent_session)
        await session.commit()
        monkeypatch.setattr(
            claude_module.os,
            "killpg",
            lambda pgid, sig: pytest.fail("remote process group must not be signaled locally"),
        )

        service = ClaudeAgentService(workspace_base_dir=tmp_path)

        aborted = await service.abort_endpoint(endpoint_model)

        assert aborted is False
        assert process_state_path.exists()
        await session.refresh(agent_session)
        assert agent_session.status == EndpointAgentSessionStatus.RUNNING

    def test_process_group_liveness_ignores_zombie_only_group(self, monkeypatch):
        class _PsResult:
            returncode = 0
            stdout = "64979 Z\n64979 Z+\n"

        def killpg(pgid, sig):
            raise PermissionError

        monkeypatch.setattr(claude_module.os, "killpg", killpg)
        monkeypatch.setattr(
            claude_module.subprocess,
            "run",
            lambda *args, **kwargs: _PsResult(),
        )

        assert claude_module._is_process_group_running(64979) is False

    def test_process_group_liveness_detects_non_zombie_member(self, monkeypatch):
        class _PsResult:
            returncode = 0
            stdout = "64979 Z\n64979 S+\n"

        def killpg(pgid, sig):
            raise PermissionError

        monkeypatch.setattr(claude_module.os, "killpg", killpg)
        monkeypatch.setattr(
            claude_module.subprocess,
            "run",
            lambda *args, **kwargs: _PsResult(),
        )

        assert claude_module._is_process_group_running(64979) is True

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
                    run_name="qwen-endpoint-1",
                    service_yaml="type: service\nname: qwen-endpoint-1\n",
                )
            )

        endpoint_model = await _create_endpoint_model(session)
        service = ClaudeAgentService(runner=runner, workspace_base_dir=tmp_path)

        result = await service.provision_endpoint(endpoint_model, pipeline_hinter=None)

        assert result.error is None
        assert result.run_id == run_id
        assert result.run_name == "qwen-endpoint-1"
        assert result.final_report is not None
        assert result.final_report.success is True
        assert (
            "`final_report.json` must contain only the schema fields"
            in captured["request"]["prompt"]
        )
        session_root = tmp_path / str(endpoint_model.id) / "1"
        assert captured["request"]["cwd"] == str(session_root / "workspace")
        env = captured["request"]["env"]
        assert env["ANTHROPIC_API_KEY"] == "agent-secret"
        agent_home = Path(env["HOME"])
        assert agent_home != session_root / "home"
        assert agent_home.resolve() == session_root / "home"
        control_sock_path = agent_home / ".dstack" / "ssh" / f"{'x' * 60}.control.sock"
        assert len(str(control_sock_path)) < 104
        assert stat.S_IMODE((session_root / "home" / ".ssh").stat().st_mode) == 0o700
        assert env["DSTACK_PROJECT"] == "main"
        assert env["DSTACK_ENDPOINT_SERVER_URL"] == "http://127.0.0.1:8000"
        assert env["DSTACK_ENDPOINT_BEARER_TOKEN"] == "user-token"
        assert env["HF_TOKEN"] == "hf-secret"
        assert "DATABASE_URL" not in env
        assert captured["request"]["options"]["model"] == "test-claude-model"
        assert "max_budget" not in captured["request"]["options"]
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
        assert "--max-budget-usd" not in command
        config = yaml.safe_load((session_root / "home" / ".dstack" / "config.yml").read_text())
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
        work_dir = session_root / "workspace"
        state = json.loads((work_dir / "agent_state.json").read_text())
        assert state["endpoint_name"] == "qwen-endpoint"
        assert state["model"] == "Qwen/Qwen3-0.6B"
        assert state["phase"] == "success"
        assert "max_agent_budget" not in state
        assert not (work_dir / "sources.jsonl").exists()
        assert (work_dir / "submissions.jsonl").exists()
        assert (work_dir / "commands.jsonl").exists()
        assert (work_dir / "progress.jsonl").exists()
        progress_helper = session_root / "bin" / "progress"
        assert progress_helper.exists()
        assert not (session_root / "bin" / "dstack").exists()
        progress_result = subprocess.run(
            [str(progress_helper), "Checked model config."],
            cwd=work_dir,
            env=captured["request"]["env"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert progress_result.returncode == 0
        assert json.loads((work_dir / "progress.jsonl").read_text().splitlines()[-1]) == {
            "message": "Checked model config."
        }
        assert not (work_dir / "hardware_reasoning.md").exists()
        assert (work_dir / ".claude" / "skills" / "dstack" / "SKILL.md").exists()
        assert (work_dir / ".claude" / "skills" / "dstack-prototyping" / "SKILL.md").exists()
        final_report = json.loads((work_dir / "final_report.json").read_text())
        assert final_report["success"] is True
        assert final_report["run_name"] == "qwen-endpoint-1"

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
                    run_name="qwen-endpoint-1",
                    service_yaml="type: service\nname: qwen-endpoint-1\n",
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
        assert "Reuse these CLI flags" not in prompt
        assert "--max-price 0.3 --on-demand" not in prompt
        assert "--availability-zone" not in prompt
        assert "--instance " not in prompt

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
                    "run_name": "qwen-endpoint-1",
                    "service_yaml": "type: service\nname: qwen-endpoint-1\n",
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
        assert result.run_name == "qwen-endpoint-1"
        assert result.final_report is not None
        assert result.final_report.success is True

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
            lambda workspace, agent_session=None: 123,
        )
        endpoint_model = await _create_endpoint_model(session)
        work_dir = tmp_path / str(endpoint_model.id) / "workspace"
        work_dir.mkdir(parents=True)
        (work_dir / "final_report.json").write_text(
            json.dumps(
                {
                    "success": True,
                    "run_id": str(uuid.uuid4()),
                    "run_name": "qwen-endpoint-1",
                    "service_yaml": "type: service\nname: qwen-endpoint-1\n",
                }
            ),
            encoding="utf-8",
        )

        service = ClaudeAgentService(workspace_base_dir=tmp_path)

        result = await service.provision_endpoint(endpoint_model, pipeline_hinter=None)

        assert result.in_progress is True
        assert result.final_report is None

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
            lambda workspace, agent_session=None: 123,
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
                    run_name="qwen-endpoint-1",
                    service_yaml="token: hf-secret\n",
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
                error="Server agent failed before returning a final report: bad key"
            )

        endpoint_model = await _create_endpoint_model(session)
        service = ClaudeAgentService(runner=runner, workspace_base_dir=tmp_path)

        result = await service.provision_endpoint(endpoint_model, pipeline_hinter=None)

        assert result.error == "Server agent failed before returning a final report: bad key"
        assert result.final_report is None
        work_dir = tmp_path / str(endpoint_model.id) / "1" / "workspace"
        state = json.loads((work_dir / "agent_state.json").read_text())
        assert state["phase"] == "failure"
        agent_error = json.loads((work_dir / "agent_error.json").read_text())
        assert agent_error["success"] is False
        assert agent_error["failure_summary"] == (
            "Server agent failed before returning a final report: bad key"
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
        )
        report = {
            "success": True,
            "run_id": str(uuid.uuid4()),
            "run_name": "qwen-endpoint-1",
            "service_yaml": "env: secret\n",
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

    def test_loads_submitted_run_names_without_run_ids(self, tmp_path):
        workspace = _AgentWorkspace(
            root_dir=tmp_path,
            home_dir=tmp_path / "home",
            work_dir=tmp_path / "work",
            trace_path=tmp_path / "trace.jsonl",
            env={},
            redacted_values=[],
            endpoint_name="qwen-endpoint",
            model="Qwen/Qwen3-0.6B",
        )
        workspace.work_dir.mkdir(parents=True)
        run_id = uuid.uuid4()
        (workspace.work_dir / "submissions.jsonl").write_text(
            "\n".join(
                [
                    json.dumps({"name": "qwen-endpoint-1", "run_id": None}),
                    json.dumps({"name": "qwen-endpoint-1", "run_id": str(run_id)}),
                    json.dumps({"name": "qwen-endpoint-2"}),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        submissions = _load_submissions(workspace)

        assert submissions.run_ids == (run_id,)
        assert submissions.run_names == ("qwen-endpoint-1", "qwen-endpoint-2")

    @pytest.mark.asyncio
    async def test_stores_assistant_text_without_copying_stream_to_endpoint_logs(
        self,
        tmp_path,
    ):
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
            log_writer=log_writer,
        )
        reader.feed_data(
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "text",
                                "text": "Checking offers without exposing secret.",
                            },
                            {
                                "type": "tool_use",
                                "id": "tool-1",
                                "name": "Bash",
                                "input": {
                                    "description": "List offers",
                                    "command": "dstack offer --gpu 1 --max-price 0.3",
                                },
                            },
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
printf '%s\\n' 'Checking recipes with secret' >> progress.jsonl
printf '%s\\n' '{"phase":"submit","message":"Submitted service run"}' >> progress.jsonl
cat > final_report.json <<'JSON'
{
  "success": true,
  "run_id": "6e578748-d597-4fde-a3a4-203587cad5a2",
  "run_name": "qwen-endpoint-1",
  "service_yaml": "type: service\\nname: qwen-endpoint-1\\n"
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
            "Checking recipes with [redacted]",
            "Submitted service run",
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
  "run_name": "qwen-endpoint-1",
  "service_yaml": "type: service\\nname: qwen-endpoint-1\\n"
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
                "json_schema": {},
            },
        }

        result = await _run_agent_in_subprocess(workspace, request)

        assert result.error is None
        assert result.report is not None
        assert result.report.success is True
        assert result.report.run_name == "qwen-endpoint-1"

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
        )
        request = {
            "prompt": "prompt",
            "env": {},
            "options": {
                "allowed_tools": "Bash",
                "disallowed_tools": "",
                "model": "test-model",
                "max_turns": 1,
                "json_schema": {},
            },
        }

        result = await _run_agent_in_subprocess(workspace, request)

        assert result.error == (
            "Server agent process exited without a final report (return code 143)"
        )
        assert "huge offer table" not in result.error
