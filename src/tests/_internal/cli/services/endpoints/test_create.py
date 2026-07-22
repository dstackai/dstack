import asyncio
import json
import os
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
    load_agent_session,
    mark_session_owner,
    print_endpoint_progress,
    print_session_log,
    release_session_claim,
    remove_agent_workspace,
    session_process_alive,
    try_claim_session,
)
from dstack._internal.cli.services.endpoints.create import (
    EndpointPresetCreateResult,
    SessionBusyError,
    _build_constraints,
    _cleanup_runs,
    _create_endpoint_preset,
    _get_build_name,
    _print_fleet_offers,
    _save_final_report_copy,
    _stop_active_session_runs,
    create_endpoint_preset,
    follow_endpoint_preset,
    reconcile_detached_sessions,
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
        assert {path.name for path in paths[0].iterdir()} == {
            "agent.log",
            "session.json",
            "preset.dstack.yml",
        }
        manifest = json.loads((paths[0] / "session.json").read_text())
        assert manifest["status"] == "success"
        assert manifest["id"] == paths[0].name
        assert "testing preset" in (paths[0] / "agent.log").read_text()

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
            "preset.dstack.yml",
            "agent.log",
            "prompt.md",
            "session.json",
            "trace.jsonl",
        }
        assert json.loads((paths[0] / "session.json").read_text())["status"] == "running"
        assert "hf-secret" not in (paths[0] / "preset.dstack.yml").read_text()
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

        with pytest.raises(CLIError, match="no fleets"):
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
    def test_derives_slug_for_nameless_and_keeps_prefix_bounded(self):
        assert _get_build_name(None, "Qwen/Qwen3.5-27B", "a1b2c3d4") == "qwen3-5-27b-a1b2c3d4"

        build_name = _get_build_name(
            "qwen-endpoint-with-a-name-that-is-forty-one", "Qwen/Qwen3.5-27B", "a1b2c3d4"
        )

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
        assert "--resume" in output
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

    @pytest.mark.asyncio
    async def test_pins_user_prompt_on_create(self, creation_context, monkeypatch, tmp_path):
        session_dir = tmp_path / "ab34ef12"
        session_dir.mkdir()
        (session_dir / "agent.log").touch()
        agent_session = EndpointAgentSession(
            path=session_dir, timestamp="t", debug=False, preset_id="ab34ef12"
        )
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

        await _create_endpoint_preset(
            api=creation_context.api,
            configuration=creation_context.configuration,
            source_configuration=creation_context.source_configuration,
            store=creation_context.store,
            build_name="qwen-build",
            agent_session=agent_session,
            user_prompt="Optimize for RAG traffic.",
        )

        assert agent_session.read_user_prompt() == "Optimize for RAG traffic."
        assert "## Additional instructions" in captured["prompt"]
        assert "Optimize for RAG traffic." in captured["prompt"]

    @pytest.mark.asyncio
    async def test_resume_keeps_the_pinned_user_prompt(
        self, creation_context, monkeypatch, tmp_path, capsys
    ):
        session_dir = tmp_path / "ab34ef12"
        session_dir.mkdir()
        (session_dir / "agent.log").touch()
        agent_session = EndpointAgentSession(
            path=session_dir, timestamp="t", debug=False, preset_id="ab34ef12"
        )
        workspace = create_agent_workspace(agent_session)
        workspace.constraints_path.write_text(
            '{"run_name_prefix": "qwen-build"}', encoding="utf-8"
        )
        agent_session.update_manifest(claude_session_id="sid-abc")
        agent_session.write_user_prompt("Optimize for RAG traffic.")
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

        await _create_endpoint_preset(
            api=creation_context.api,
            configuration=creation_context.configuration,
            source_configuration=creation_context.source_configuration,
            store=creation_context.store,
            agent_session=agent_session,
            resume=True,
            user_prompt="A different prompt.",
        )

        # The session keeps its original prompt; the new one is ignored with a warning.
        assert "Optimize for RAG traffic." in captured["prompt"]
        assert "A different prompt." not in captured["prompt"]
        assert "keepsitsoriginalprompt" in "".join(capsys.readouterr().out.split())
        remove_agent_workspace(agent_session)


class TestFleetOffersPreview:
    def test_no_offers_shows_the_shared_warning_without_failing(self, capsys):
        plan = SimpleNamespace(
            project_name="main",
            user="admin",
            job_plans=[SimpleNamespace(offers=[], total_offers=0, max_price=None)],
        )
        api = SimpleNamespace(
            project="main",
            client=SimpleNamespace(runs=SimpleNamespace(get_plan=lambda *a, **k: plan)),
        )

        _print_fleet_offers(api, ("arm-fleet",))

        out = capsys.readouterr().out
        assert "arm-fleet" in out
        assert "No matching instance offers available" in out


class TestSessionLog:
    def _session(self, tmp_path, preset_id: str, status: str, log: str) -> EndpointAgentSession:
        session_dir = tmp_path / preset_id
        session_dir.mkdir()
        (session_dir / "agent.log").write_text(log)
        session = EndpointAgentSession(
            path=session_dir, timestamp="t", debug=False, preset_id=preset_id
        )
        session.update_manifest(status=status)
        return session

    def test_load_agent_session_reads_any_status(self, tmp_path, monkeypatch):
        self._session(tmp_path, "dead0000", "failed", "[t] boom\n")
        monkeypatch.setattr(
            "dstack._internal.cli.services.endpoints.agent.get_presets_dir",
            lambda: tmp_path,
        )
        # A failed session is off-limits to follow/resume, but its log is readable.
        session = load_agent_session("dead0000")
        assert session.preset_id == "dead0000"
        with pytest.raises(CLIError, match="Unknown preset"):
            load_agent_session("nope0000")

    def test_print_session_log_dumps_log_verbatim(self, tmp_path, monkeypatch, capsys):
        session = self._session(
            tmp_path, "abcd0000", "success", "[t] trial 1 done\n[t] saved preset\n"
        )
        print_session_log(session)
        out = capsys.readouterr().out
        assert "trial 1 done" in out
        assert "saved preset" in out

    def test_print_session_log_notes_empty_log(self, tmp_path, capsys):
        session = self._session(tmp_path, "empty000", "running", "")
        print_session_log(session)
        assert "No log output yet" in capsys.readouterr().out


class TestFollowEndpointPreset:
    def _detached_session(self, tmp_path, configuration_yaml: str) -> EndpointAgentSession:
        session_dir = tmp_path / "ab12cd34"
        session_dir.mkdir()
        (session_dir / "agent.log").touch()
        (session_dir / "preset.dstack.yml").write_text(configuration_yaml)
        session = EndpointAgentSession(
            path=session_dir, timestamp="t", debug=False, preset_id="ab12cd34"
        )
        workspace = create_agent_workspace(session)
        workspace.constraints_path.write_text('{"run_name_prefix": "qwen-build"}')
        session.update_manifest(status="running", agent_pid=987654321)
        return session

    def test_finalizes_a_detached_session(self, creation_context, monkeypatch, tmp_path):
        session = self._detached_session(
            tmp_path, "type: preset\nname: qwen\nmodel:\n  base: Qwen/Qwen3.5-27B\n"
        )
        monkeypatch.setattr(
            "dstack._internal.cli.services.endpoints.agent.get_presets_dir",
            lambda: tmp_path,
        )
        monkeypatch.setattr(
            "dstack._internal.cli.services.endpoints.create.load_attachable_agent_session",
            lambda preset_id: session,
        )

        async def fake_attach(**kwargs):
            return EndpointAgentProcessOutput(
                report_data=json.loads(get_successful_endpoint_report(creation_context.run).json())
            )

        monkeypatch.setattr(
            "dstack._internal.cli.services.endpoints.create.attach_endpoint_agent",
            fake_attach,
        )

        result = follow_endpoint_preset(
            api=creation_context.api,
            store=creation_context.store,
            preset_id="ab12cd34",
        )

        assert result.preset.id == "ab12cd34"
        assert creation_context.store.get("ab12cd34") is not None
        assert session.read_manifest()["status"] == "success"

    def test_agent_death_without_report_suspends_instead_of_failing(
        self, creation_context, monkeypatch, tmp_path
    ):
        session = self._detached_session(
            tmp_path, "type: preset\nname: qwen\nmodel:\n  base: Qwen/Qwen3.5-27B\n"
        )
        monkeypatch.setattr(
            "dstack._internal.cli.services.endpoints.create.load_attachable_agent_session",
            lambda preset_id: session,
        )

        async def fake_attach(**kwargs):
            return EndpointAgentProcessOutput(error="agent died")

        monkeypatch.setattr(
            "dstack._internal.cli.services.endpoints.create.attach_endpoint_agent",
            fake_attach,
        )

        with pytest.raises(CLIError, match="agent died"):
            follow_endpoint_preset(
                api=creation_context.api,
                store=creation_context.store,
                preset_id="ab12cd34",
            )

        assert session.read_manifest()["status"] == "interrupted"

    def test_backs_off_when_claim_is_held(self, creation_context, monkeypatch, tmp_path):
        session = self._detached_session(
            tmp_path, "type: preset\nname: qwen\nmodel:\n  base: Qwen/Qwen3.5-27B\n"
        )
        # Another live holder owns the finalize lock (reconcile or logs -f).
        held = try_claim_session(session)
        assert held is not None
        monkeypatch.setattr(
            "dstack._internal.cli.services.endpoints.create.load_attachable_agent_session",
            lambda preset_id: session,
        )
        # claim=True must refuse rather than double-finalize; the session is untouched.
        with pytest.raises(SessionBusyError):
            follow_endpoint_preset(
                api=creation_context.api,
                store=creation_context.store,
                preset_id="ab12cd34",
                claim=True,
            )
        assert session.read_manifest()["status"] == "running"
        release_session_claim(held)


class TestStopActiveSessionRuns:
    def _session(self, tmp_path) -> EndpointAgentSession:
        session_dir = tmp_path / "ab12cd34"
        session_dir.mkdir()
        (session_dir / "runs.jsonl").write_text(
            '{"name":"qwen-build-1","id":"a"}\n{"name":"qwen-build-2","id":"b"}\n'
        )
        return EndpointAgentSession(
            path=session_dir, timestamp="t", debug=False, preset_id="ab12cd34"
        )

    def _api(self, statuses: dict, stopped: list) -> SimpleNamespace:
        def get(project, name):
            return SimpleNamespace(status=statuses[name])

        def stop(project, names, abort):
            stopped.extend(names)

        return SimpleNamespace(
            project="main",
            client=SimpleNamespace(runs=SimpleNamespace(get=get, stop=stop)),
        )

    def test_stops_only_non_terminal_runs(self, tmp_path):
        from dstack._internal.core.models.runs import RunStatus

        stopped: list = []
        api = self._api(
            {"qwen-build-1": RunStatus.DONE, "qwen-build-2": RunStatus.RUNNING}, stopped
        )

        # No per-run prompt: active runs are stopped automatically (like dstack stop).
        _stop_active_session_runs(api, self._session(tmp_path))
        assert stopped == ["qwen-build-2"]

    def test_stops_nothing_when_all_terminal(self, tmp_path):
        from dstack._internal.core.models.runs import RunStatus

        stopped: list = []
        api = self._api({"qwen-build-1": RunStatus.DONE, "qwen-build-2": RunStatus.DONE}, stopped)

        _stop_active_session_runs(api, self._session(tmp_path))
        assert stopped == []


class TestReconcileDetachedSessions:
    def _session_dir(
        self,
        tmp_path,
        preset_id="dead0001",
        *,
        status="running",
        project="main",
        with_report=True,
        keep_service=False,
        owner_alive=False,
    ):
        session_dir = tmp_path / preset_id
        (session_dir / "workspace" / "w").mkdir(parents=True)
        manifest = {
            "id": preset_id,
            "status": status,
            "keep_service": keep_service,
            # A dead pid unless a live owner is requested below.
            "pid": 987654321,
            "pid_started_at": 0.0,
            "workspace": str(session_dir / "workspace"),
        }
        if project is not None:
            manifest["project"] = project
        if owner_alive:
            # A live pid with no recorded start time reads as an active owner.
            manifest["agent_pid"] = os.getpid()
        (session_dir / "session.json").write_text(json.dumps(manifest))
        if with_report:
            (session_dir / "workspace" / "w" / "final_report.json").write_text("{}")
        return session_dir

    def _patch(self, monkeypatch, tmp_path, follow):
        # reconcile iterates via agent.iter_agent_sessions -> agent.get_presets_dir.
        monkeypatch.setattr(
            "dstack._internal.cli.services.endpoints.agent.get_presets_dir",
            lambda: tmp_path,
        )
        monkeypatch.setattr(
            "dstack._internal.cli.services.endpoints.create.Client",
            SimpleNamespace(from_config=lambda project_name=None: SimpleNamespace()),
        )
        monkeypatch.setattr(
            "dstack._internal.cli.services.endpoints.create.follow_endpoint_preset",
            follow,
        )

    def _recording_follow(self, calls):
        def follow(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                preset=SimpleNamespace(id=kwargs["preset_id"], base="Qwen/Qwen3.5-27B")
            )

        return follow

    def test_finalizes_eligible_detached_session(self, tmp_path, monkeypatch):
        self._session_dir(tmp_path, keep_service=True)
        calls: list = []
        self._patch(monkeypatch, tmp_path, self._recording_follow(calls))
        reconcile_detached_sessions(EndpointPresetStore(tmp_path / "store"))
        assert len(calls) == 1
        assert calls[0]["preset_id"] == "dead0001"
        # Honors persisted keep-service; non-interactive, non-blocking, silent,
        # and under the finalize claim (parallel-safe).
        assert calls[0]["keep_service"] is True
        assert calls[0]["wait_for_run_stop"] is False
        assert calls[0]["echo"] is False
        assert calls[0]["claim"] is True

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"status": "success"},
            {"status": "failed"},
            {"with_report": False},
            {"project": None},
            {"owner_alive": True},
            # `interrupted` is `stop`'s job now, not reconcile's — with or without a report.
            {"status": "interrupted"},
            {"status": "interrupted", "with_report": False},
        ],
    )
    def test_skips_ineligible(self, tmp_path, monkeypatch, kwargs):
        self._session_dir(tmp_path, **kwargs)
        calls: list = []
        self._patch(monkeypatch, tmp_path, self._recording_follow(calls))
        reconcile_detached_sessions(EndpointPresetStore(tmp_path / "store"))
        assert calls == []

    def test_never_raises_when_finalize_fails(self, tmp_path, monkeypatch):
        self._session_dir(tmp_path)

        def boom(**kwargs):
            raise RuntimeError("finalize blew up")

        self._patch(monkeypatch, tmp_path, boom)
        # A read command must never fail because reconcile did.
        reconcile_detached_sessions(EndpointPresetStore(tmp_path / "store"))


class TestSessionClaim:
    def _session(self, tmp_path):
        (tmp_path / "sess").mkdir()
        return EndpointAgentSession(
            path=tmp_path / "sess", timestamp="", debug=False, preset_id="sess"
        )

    def test_claim_is_exclusive_and_releasable(self, tmp_path):
        session = self._session(tmp_path)
        first = try_claim_session(session)
        assert first is not None
        assert try_claim_session(session) is None  # the kernel lock is held
        release_session_claim(first)
        again = try_claim_session(session)
        assert again is not None
        release_session_claim(again)

    def test_claim_acquires_when_lock_file_is_unheld(self, tmp_path):
        session = self._session(tmp_path)
        # A leftover lock file from a crashed run holds no kernel lock: the file's
        # presence must not block a new claim (no stale-lock reasoning needed).
        (session.path / ".reconcile.lock").write_text("stale")
        fd = try_claim_session(session)
        assert fd is not None
        release_session_claim(fd)


class TestSessionProcessAlive:
    def test_recycled_pid_with_stale_start_time_is_not_alive(self):
        # A live pid whose recorded start time does not match — the pid was recycled.
        assert session_process_alive({"agent_pid": os.getpid(), "agent_started_at": 0.0}) is False

    def test_dead_pids_are_not_alive(self):
        assert session_process_alive({"pid": 987654321, "pid_started_at": 0.0}) is False
        assert session_process_alive({}) is False


class TestMarkSessionOwner:
    def test_persists_finalize_context(self, tmp_path):
        (tmp_path / "s").mkdir()
        session = EndpointAgentSession(
            path=tmp_path / "s", timestamp="", debug=False, preset_id="s"
        )
        session.update_manifest(status="running")
        mark_session_owner(session, project="main", keep_service=True)
        manifest = session.read_manifest()
        assert manifest["project"] == "main"
        assert manifest["keep_service"] is True
        assert manifest["pid"] == os.getpid()
        assert "pid_started_at" in manifest
