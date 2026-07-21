import asyncio
import json
import uuid
from types import SimpleNamespace

import pytest

from dstack._internal.cli.models.endpoints import EndpointConfiguration
from dstack._internal.cli.services.endpoints.agent import (
    ClaudeAuth,
    EndpointAgentProcessOutput,
    EndpointAgentSession,
    EndpointAgentWorkspace,
    create_agent_workspace,
    print_endpoint_progress,
    remove_agent_workspace,
)
from dstack._internal.cli.services.endpoints.create import (
    EndpointPresetCreateResult,
    _build_constraints,
    _cleanup_runs,
    _create_endpoint_preset,
    _get_build_name,
    _save_final_report_copy,
    create_endpoint_preset,
)
from dstack._internal.cli.services.endpoints.store import EndpointPresetStore
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.envs import EnvSentinel
from dstack._internal.core.models.runs import Run, RunStatus
from tests._internal.cli.endpoint_presets import (
    get_endpoint_preset,
    get_running_service_run,
    get_successful_endpoint_report,
)

pytestmark = pytest.mark.windows


def _claude_auth() -> ClaudeAuth:
    return ClaudeAuth(
        api_key="anthropic-secret",
        executable="claude",
        effort=None,
        model="claude-test",
    )


@pytest.fixture
def creation_context(tmp_path, monkeypatch):
    run = get_running_service_run()
    run_apis = _FakeRunAPIs(run)
    api = SimpleNamespace(
        project="main",
        runs=run_apis,
        client=SimpleNamespace(
            _token="dstack-secret",
            base_url="http://127.0.0.1:3000",
            runs=run_apis,
        ),
    )
    configuration = EndpointConfiguration(
        name="qwen-build",
        model={"base": "Qwen/Qwen3.5-27B"},
        context_length=8192,
        fleets=["gpu-fleet"],
        env={"LICENSE": "license-secret", "TOKENIZERS_PARALLELISM": "false"},
    )
    source_configuration = EndpointConfiguration(
        name="qwen-build",
        model={"base": "Qwen/Qwen3.5-27B"},
        context_length=8192,
        fleets=["gpu-fleet"],
        env=["LICENSE", "TOKENIZERS_PARALLELISM=false"],
    )
    monkeypatch.setattr(
        "dstack._internal.cli.services.endpoints.create.get_claude_auth",
        _claude_auth,
    )
    monkeypatch.setattr(
        "dstack._internal.cli.services.endpoints.create._get_build_name",
        lambda *_: "qwen-build",
    )
    return SimpleNamespace(
        api=api,
        configuration=configuration,
        source_configuration=source_configuration,
        run=run,
        run_apis=run_apis,
        store=EndpointPresetStore(tmp_path / "presets"),
    )


class TestCreateEndpointPreset:
    def test_saves_agent_log_without_debug(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        preset = get_endpoint_preset()

        async def create(**kwargs):
            print_endpoint_progress("testing preset", agent_session=kwargs["agent_session"])
            return EndpointPresetCreateResult(
                preset=preset,
                path=tmp_path / "preset.yaml",
                final_run_id=uuid.uuid4(),
                final_run_name="qwen-build-2",
            )

        monkeypatch.setattr(
            "dstack._internal.cli.services.endpoints.create._create_endpoint_preset",
            create,
        )

        create_endpoint_preset(
            api=SimpleNamespace(),
            configuration=EndpointConfiguration(
                name="qwen",
                model={"base": "Qwen/Qwen3.5-27B"},
            ),
            store=EndpointPresetStore(tmp_path / "presets"),
        )

        paths = [
            path
            for path in (tmp_path / ".dstack" / "presets").iterdir()
            if path.is_dir() and not path.name.startswith(".")
        ]
        assert len(paths) == 1
        assert {path.name for path in paths[0].iterdir()} == {"agent.log", "session.json"}
        manifest = json.loads((paths[0] / "session.json").read_text())
        assert manifest["status"] == "success"
        assert manifest["id"] == paths[0].name
        assert "testing preset" in (paths[0] / "agent.log").read_text()
        output = capsys.readouterr().out.replace("\n", "")
        assert f"Agent log saved to {paths[0] / 'agent.log'}" in output

    def test_debug_finalization_error_does_not_mask_success(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.setenv("HF_TOKEN", "hf-secret")
        preset = get_endpoint_preset()

        async def create(**kwargs):
            assert kwargs["configuration"].env.as_dict() == {
                "HF_TOKEN": "hf-secret",
                "TOKENIZERS_PARALLELISM": "false",
            }
            assert isinstance(kwargs["source_configuration"].env["HF_TOKEN"], EnvSentinel)
            assert kwargs["source_configuration"].env["TOKENIZERS_PARALLELISM"] == "false"
            kwargs["agent_session"].write_prompt("test prompt")
            return EndpointPresetCreateResult(
                preset=preset,
                path=tmp_path / "preset.yaml",
                final_run_id=uuid.uuid4(),
                final_run_name="qwen-build-2",
            )

        def fail_finish(self, preset_id=None):
            raise OSError("rename failed")

        monkeypatch.setattr(
            "dstack._internal.cli.services.endpoints.create._create_endpoint_preset",
            create,
        )
        monkeypatch.setattr(EndpointAgentSession, "finish", fail_finish)

        result = create_endpoint_preset(
            api=SimpleNamespace(),
            configuration=EndpointConfiguration(
                name="qwen",
                model={"base": "Qwen/Qwen3.5-27B"},
                env=["HF_TOKEN", "TOKENIZERS_PARALLELISM=false"],
            ),
            store=EndpointPresetStore(tmp_path / "presets"),
            debug=True,
        )

        paths = [
            path
            for path in (tmp_path / ".dstack" / "presets").iterdir()
            if path.is_dir() and not path.name.startswith(".")
        ]
        assert len(paths) == 1
        assert result.preset == preset
        assert {path.name for path in paths[0].iterdir()} == {
            "endpoint.dstack.yml",
            "agent.log",
            "prompt.md",
            "session.json",
            "trace.jsonl",
        }
        assert json.loads((paths[0] / "session.json").read_text())["status"] == "running"
        assert "hf-secret" not in (paths[0] / "endpoint.dstack.yml").read_text()
        assert "Files remain at" in capsys.readouterr().out

    def test_debug_finalization_does_not_mask_creation_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))

        async def create(**kwargs):
            raise RuntimeError("creation failed")

        def fail_finish(self, preset_id=None):
            raise OSError("rename failed")

        monkeypatch.setattr(
            "dstack._internal.cli.services.endpoints.create._create_endpoint_preset",
            create,
        )
        monkeypatch.setattr(EndpointAgentSession, "finish", fail_finish)

        with pytest.raises(RuntimeError, match="creation failed"):
            create_endpoint_preset(
                api=SimpleNamespace(),
                configuration=EndpointConfiguration(
                    name="qwen",
                    model={"base": "Qwen/Qwen3.5-27B"},
                ),
                store=EndpointPresetStore(tmp_path / "presets"),
                debug=True,
            )

    @pytest.mark.asyncio
    async def test_checks_active_fleets_before_claude_auth(self, tmp_path, monkeypatch):
        api = SimpleNamespace(
            project="main",
            client=SimpleNamespace(fleets=SimpleNamespace(list=lambda *args, **kwargs: [])),
        )
        monkeypatch.setattr(
            "dstack._internal.cli.services.endpoints.create.get_claude_auth",
            lambda: pytest.fail("Claude auth must not be checked without an active fleet"),
        )

        with pytest.raises(CLIError, match="no active fleets"):
            await _create_endpoint_preset(
                api=api,
                configuration=EndpointConfiguration(
                    name="qwen-build",
                    model={"base": "Qwen/Qwen3.5-27B"},
                ),
                store=EndpointPresetStore(tmp_path / "presets"),
                agent_session=_agent_session(tmp_path),
            )

    @pytest.mark.asyncio
    async def test_skips_cleanup_when_cancelled(self, creation_context, monkeypatch, tmp_path):
        async def run_agent(**_):
            raise asyncio.CancelledError

        cleanup_calls = []

        async def cleanup_runs(**kwargs):
            cleanup_calls.append(kwargs)

        monkeypatch.setattr(
            "dstack._internal.cli.services.endpoints.create.run_endpoint_agent",
            run_agent,
        )
        monkeypatch.setattr(
            "dstack._internal.cli.services.endpoints.create._cleanup_runs",
            cleanup_runs,
        )

        with pytest.raises(asyncio.CancelledError):
            await _create_endpoint_preset(
                api=creation_context.api,
                configuration=creation_context.configuration,
                source_configuration=creation_context.source_configuration,
                store=creation_context.store,
                agent_session=_agent_session(tmp_path),
            )

        assert cleanup_calls == []

    @pytest.mark.parametrize(
        ("keep_service", "stopped_names"),
        [(False, ["qwen-build-2"]), (True, [])],
    )
    @pytest.mark.asyncio
    async def test_saves_preset_and_cleans_up_runs(
        self, creation_context, monkeypatch, keep_service, stopped_names, tmp_path
    ):
        session_path = tmp_path / "debug-running"
        session_path.mkdir()
        (session_path / "agent.log").touch()
        (session_path / "trace.jsonl").touch()
        agent_session = EndpointAgentSession(
            path=session_path,
            timestamp="20260714-120000Z",
            debug=True,
        )

        async def run_agent(**kwargs):
            assert kwargs["agent_session"] is agent_session
            assert (session_path / "prompt.md").is_file()
            return EndpointAgentProcessOutput(
                report_data=json.loads(get_successful_endpoint_report(creation_context.run).json())
            )

        monkeypatch.setattr(
            "dstack._internal.cli.services.endpoints.create.run_endpoint_agent",
            run_agent,
        )
        result = await _create_endpoint_preset(
            api=creation_context.api,
            configuration=creation_context.configuration,
            source_configuration=creation_context.source_configuration,
            store=creation_context.store,
            keep_service=keep_service,
            build_name="qwen-build",
            agent_session=agent_session,
        )

        assert result.preset.base == "Qwen/Qwen3.5-27B"
        assert result.path.is_file()
        assert creation_context.store.list() == [result.preset]
        assert "license-secret" not in result.path.read_text()
        assert result.preset.service.env["TOKENIZERS_PARALLELISM"] == "false"
        assert creation_context.run_apis.stopped_names == stopped_names


class TestBuildName:
    def test_requires_name_and_keeps_generated_prefix_bounded(self):
        with pytest.raises(CLIError, match="Endpoint name is required"):
            _get_build_name(None, "a1b2c3d4")

        build_name = _get_build_name("qwen-endpoint-with-a-name-that-is-forty-one", "a1b2c3d4")

        assert build_name.endswith("-a1b2c3d4")
        assert len(f"{build_name}-99999") <= 41


class TestCleanupRuns:
    @pytest.mark.asyncio
    async def test_stops_only_recorded_build_runs(self, tmp_path, monkeypatch):
        (tmp_path / "runs.jsonl").write_text(
            '{"name":"qwen-build-1"}\n{"name":"unrelated-run"}\n{"name":"qwen-build-2"}\n'
        )
        runs = _FakeRuns()
        api = SimpleNamespace(
            runs=runs,
            project="main",
            client=SimpleNamespace(runs=runs),
        )

        async def no_sleep(_):
            return None

        monkeypatch.setattr(asyncio, "sleep", no_sleep)
        await _cleanup_runs(
            api=api,
            build_name="qwen-build",
            workspace=EndpointAgentWorkspace(
                path=tmp_path,
                dstack_home=tmp_path / "home",
            ),
            final_run_name="qwen-build-2",
            keep_final_service=True,
            agent_session=_agent_session(tmp_path),
        )

        assert runs.stopped_names == ["qwen-build-1"]


def _agent_session(tmp_path, *, debug: bool = False) -> EndpointAgentSession:
    path = tmp_path / "agent-running"
    path.mkdir()
    (path / "agent.log").touch()
    if debug:
        (path / "trace.jsonl").touch()
    return EndpointAgentSession(
        path=path,
        timestamp="20260714-120000Z",
        debug=debug,
        preset_id="ab12cd34",
    )


class _FakeRuns:
    def __init__(self):
        self.stopped_names: list[str] = []

    def get(self, name):
        status = RunStatus.TERMINATED if name in self.stopped_names else RunStatus.RUNNING
        return SimpleNamespace(status=status)

    def stop(self, project, names, abort):
        assert project == "main"
        assert abort is False
        self.stopped_names.extend(names)


class _FakeRunAPIs:
    def __init__(self, run: Run):
        self.run = run
        self.stopped_names: list[str] = []

    def get(self, *args):
        name = args[-1]
        return self.run if name == self.run.run_spec.run_name else None

    def stop(self, project, names, abort):
        assert project == "main"
        assert abort is False
        self.stopped_names.extend(names)
        self.run.status = RunStatus.TERMINATED


class TestBuildConstraints:
    def test_renders_all_fields_with_explicit_nulls_and_defaults(self):
        configuration = EndpointConfiguration(
            name="qwen",
            model={"base": "Qwen/Qwen3-32B"},
            env=["HF_TOKEN"],
        )

        text = _build_constraints(
            configuration=configuration,
            build_name="qwen-abc123",
            allowed_fleets=("gpu-fleet",),
        )

        assert text.endswith("\n")
        assert json.loads(text) == {
            "run_name_prefix": "qwen-abc123",
            "model": {"base": "Qwen/Qwen3-32B"},
            "context_length": None,
            "max_trials": 3,
            "concurrency": 8,
            "fleets": ["gpu-fleet"],
            "env": ["HF_TOKEN"],
        }

    def test_renders_configured_values(self):
        configuration = EndpointConfiguration(
            name="qwen",
            model={"repo": "Qwen/Qwen3-32B-AWQ", "name": "qwen3"},
            context_length=32768,
            max_trials=10,
            concurrency=16,
        )

        data = json.loads(
            _build_constraints(
                configuration=configuration,
                build_name="qwen-abc123",
                allowed_fleets=("a", "b"),
            )
        )

        assert data["model"] == {"repo": "Qwen/Qwen3-32B-AWQ", "name": "qwen3"}
        assert data["context_length"] == 32768
        assert data["max_trials"] == 10
        assert data["concurrency"] == 16
        assert data["fleets"] == ["a", "b"]


class TestSaveFinalReportCopy:
    def test_copies_report_redacted(self, tmp_path):
        workspace = EndpointAgentWorkspace(path=tmp_path / "w", dstack_home=tmp_path / "h")
        workspace.path.mkdir()
        workspace.final_report_path.write_text(
            '{"success": true, "note": "token dstack-secret"}', encoding="utf-8"
        )
        session = _agent_session(tmp_path, debug=True)

        _save_final_report_copy(
            workspace=workspace,
            agent_session=session,
            redacted_values=["dstack-secret"],
        )

        copied = (session.path / "final_report.json").read_text()
        assert "dstack-secret" not in copied
        assert "[redacted]" in copied

    def test_missing_report_is_no_op(self, tmp_path):
        workspace = EndpointAgentWorkspace(path=tmp_path / "w", dstack_home=tmp_path / "h")
        workspace.path.mkdir()
        session = _agent_session(tmp_path, debug=True)

        _save_final_report_copy(
            workspace=workspace,
            agent_session=session,
            redacted_values=["dstack-secret"],
        )

        assert not (session.path / "final_report.json").exists()


class TestInterruptAndResume:
    def test_interrupt_suspends_session(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))

        async def create(**kwargs):
            raise KeyboardInterrupt

        monkeypatch.setattr(
            "dstack._internal.cli.services.endpoints.create._create_endpoint_preset",
            create,
        )

        with pytest.raises(KeyboardInterrupt):
            create_endpoint_preset(
                api=SimpleNamespace(),
                configuration=EndpointConfiguration(
                    name="qwen", model={"base": "Qwen/Qwen3.5-27B"}
                ),
                store=EndpointPresetStore(tmp_path / "presets"),
            )

        sessions = [
            path
            for path in (tmp_path / ".dstack" / "presets").iterdir()
            if path.is_dir() and not path.name.startswith(".")
        ]
        assert len(sessions) == 1
        manifest = json.loads((sessions[0] / "session.json").read_text())
        assert manifest["status"] == "interrupted"
        output = capsys.readouterr().out
        assert "Resume with" in output
        assert sessions[0].name in output

    @pytest.mark.asyncio
    async def test_resume_uses_saved_claude_session(self, creation_context, monkeypatch, tmp_path):
        session_dir = tmp_path / "sessions" / "fe98dc76"
        session_dir.mkdir(parents=True)
        (session_dir / "agent.log").touch()
        agent_session = EndpointAgentSession(
            path=session_dir, timestamp="t", debug=False, preset_id="fe98dc76"
        )
        workspace = create_agent_workspace(agent_session)
        workspace.constraints_path.write_text(
            '{"run_name_prefix": "qwen-build"}', encoding="utf-8"
        )
        agent_session.update_manifest(claude_session_id="sid-xyz", claude_model="claude-pinned")
        captured = {}

        async def run_agent(**kwargs):
            captured.update(kwargs)
            return EndpointAgentProcessOutput(
                report_data=json.loads(get_successful_endpoint_report(creation_context.run).json())
            )

        monkeypatch.setattr(
            "dstack._internal.cli.services.endpoints.create.run_endpoint_agent",
            run_agent,
        )

        result = await _create_endpoint_preset(
            api=creation_context.api,
            configuration=creation_context.configuration,
            source_configuration=creation_context.source_configuration,
            store=creation_context.store,
            agent_session=agent_session,
            resume=True,
        )

        assert captured["initial_resume_session_id"] == "sid-xyz"
        assert captured["auth"].model == "claude-pinned"
        assert result.preset.id == "fe98dc76"
        assert (session_dir / "workspace").is_dir()
        remove_agent_workspace(agent_session)
