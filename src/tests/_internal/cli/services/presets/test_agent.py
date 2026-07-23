import asyncio
import json
import os
import shutil
import signal
import subprocess
import sys
from contextlib import suppress
from pathlib import Path
from types import SimpleNamespace

import psutil
import pytest
import yaml

from dstack._internal.cli.models.configurations import PresetConfiguration
from dstack._internal.cli.services.presets.agent import (
    ClaudeAuth,
    _build_claude_command,
    _prepare_subprocess_command,
    _terminate_process,
    build_preset_agent_env,
    get_claude_auth,
    run_preset_agent,
)
from dstack._internal.cli.services.presets.redaction import (
    contains_redacted_value,
    redact,
)
from dstack._internal.cli.services.presets.session import (
    PresetAgentSession,
    _summarize_session_trials,
    create_preset_agent_session,
    load_resumable_agent_session,
    print_preset_progress,
)
from dstack._internal.cli.services.presets.tail import (
    _ProgressTailer,
    _RecordMirror,
)
from dstack._internal.cli.services.presets.workspace import (
    PresetAgentWorkspace,
    attach_agent_workspace,
    create_agent_workspace,
    remove_agent_workspace,
)
from dstack._internal.compat import IS_WINDOWS
from dstack._internal.core.errors import CLIError
from dstack._internal.core.services.configs import ConfigManager

pytestmark = pytest.mark.windows


def _claude_auth(*, api_key: str | None = "anthropic-secret", effort=None) -> ClaudeAuth:
    return ClaudeAuth(
        api_key=api_key,
        executable="claude",
        effort=effort,
        model="claude-test",
    )


class TestClaudeAuth:
    @pytest.mark.parametrize("api_key_env", ["key", None])
    def test_uses_api_key_only_when_env_is_set(self, monkeypatch, api_key_env):
        if api_key_env is None:
            monkeypatch.delenv("DSTACK_AGENT_ANTHROPIC_API_KEY", raising=False)
        else:
            monkeypatch.setenv("DSTACK_AGENT_ANTHROPIC_API_KEY", api_key_env)
        monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/claude")

        auth = get_claude_auth()

        assert auth.api_key == api_key_env

    @pytest.mark.parametrize("api_key", ["key", None])
    def test_builds_command_for_selected_auth_mode(self, api_key):
        command = _build_claude_command(auth=_claude_auth(api_key=api_key, effort="high"))

        assert ("--bare" in command) is (api_key is not None)
        assert ("--setting-sources" in command) is (api_key is None)
        assert command[command.index("--effort") + 1] == "high"

    @pytest.mark.windows_only
    def test_runs_windows_batch_launcher(self, tmp_path):
        script = tmp_path / "fake-claude.cmd"
        script.write_text("@echo off\necho batch-ok\n")

        result = subprocess.run(
            _prepare_subprocess_command([str(script)]),
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert result.stdout.strip() == "batch-ok"


class TestAgentIsolation:
    def test_inherits_only_required_environment(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PATH", "/usr/bin")
        monkeypatch.setenv("HOME", "/home/test")
        monkeypatch.setenv("UNRELATED_SECRET", "must-not-be-inherited")
        api = SimpleNamespace(
            project="main",
            client=SimpleNamespace(base_url="http://127.0.0.1:3000"),
        )

        env = build_preset_agent_env(
            api=api,
            preset_env={"HF_TOKEN": "hf-secret"},
            auth=_claude_auth(),
            workspace=PresetAgentWorkspace(
                path=tmp_path,
                dstack_home=tmp_path / "home",
            ),
            token="dstack-secret",
        )

        assert env["DSTACK_SERVER_URL"] == "http://127.0.0.1:3000"
        assert env["DSTACK_PROJECT"] == "main"
        assert env["DSTACK_TOKEN"] == "dstack-secret"
        assert env["HF_TOKEN"] == "hf-secret"
        assert env["ANTHROPIC_API_KEY"] == "anthropic-secret"
        assert env["HOME"] == str(tmp_path / "home")
        assert "UNRELATED_SECRET" not in env
        project = ConfigManager(tmp_path / "home" / ".dstack").get_project_config()
        assert project is not None
        assert project.name == "main"
        assert project.url == "http://127.0.0.1:3000"
        assert project.token == "dstack-secret"

    def test_creates_private_cli_home_and_dstack_wrapper(self, tmp_path):
        workspace = _session_workspace(tmp_path)
        if not IS_WINDOWS:
            assert (workspace.dstack_home / ".ssh").stat().st_mode & 0o777 == 0o700
        assert not (workspace.dstack_home / ".dstack" / "config.yml").exists()
        dstack_command = shutil.which("dstack", path=str(workspace.bin_path))
        assert dstack_command is not None
        result = subprocess.run(
            [dstack_command, "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Usage: dstack" in result.stdout

    def test_keeps_control_socket_path_bounded(self, tmp_path):
        workspace = _session_workspace(tmp_path)
        if not IS_WINDOWS:
            socket_path = workspace.dstack_home / ".dstack" / "ssh" / f"{'x' * 41}.control.sock"
            assert len(os.fsencode(socket_path)) <= 103

    def test_detects_known_secret_in_generated_artifact(self):
        assert contains_redacted_value(
            {"commands": ["serve --token secret-token"]},
            ("secret-token",),
        )


def _session_workspace(tmp_path):
    session_dir = tmp_path / "session-under-test"
    session_dir.mkdir()
    session = PresetAgentSession(path=session_dir, debug=False, preset_id="abcd1234")
    return create_agent_workspace(session)


class TestAgentSession:
    def _configuration(self) -> PresetConfiguration:
        return PresetConfiguration(
            name="qwen",
            model={"base": "Qwen/Qwen3.5-27B"},
            max_price=0.5,
            env=["HF_TOKEN", "TOKENIZERS_PARALLELISM=false"],
        )

    def _home(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))

    def test_creates_private_session_with_log_and_manifest(self, tmp_path, monkeypatch, capsys):
        self._home(tmp_path, monkeypatch)

        session = create_preset_agent_session(self._configuration())

        assert session.path.parent == tmp_path / ".dstack" / "presets"
        assert session.path.name == session.preset_id
        assert len(session.preset_id) == 8
        assert {path.name for path in session.path.iterdir()} == {
            "agent.log",
            "session.json",
            "preset.dstack.yml",
        }
        manifest = json.loads((session.path / "session.json").read_text())
        assert manifest["id"] == session.preset_id
        assert manifest["status"] == "running"
        assert manifest["name"] == "qwen"
        assert manifest["model"] == "Qwen/Qwen3.5-27B"
        assert manifest["pid"] == os.getpid()
        print_preset_progress("creating preset", agent_session=session)
        assert "creating preset" in session.log_path.read_text()
        assert "creating preset" in capsys.readouterr().out
        if not IS_WINDOWS:
            assert session.path.stat().st_mode & 0o777 == 0o700
            assert session.log_path.stat().st_mode & 0o777 == 0o600

    def test_debug_session_saves_scrubbed_configuration_and_trace(self, tmp_path, monkeypatch):
        self._home(tmp_path, monkeypatch)

        debug_session = create_preset_agent_session(self._configuration(), debug=True)

        data = yaml.safe_load((debug_session.path / "preset.dstack.yml").read_text())
        assert {path.name for path in debug_session.path.iterdir()} == {
            "agent.log",
            "preset.dstack.yml",
            "session.json",
            "trace.jsonl",
        }
        assert data["max_price"] == 0.5
        assert data["env"] == ["HF_TOKEN", "TOKENIZERS_PARALLELISM"]
        assert "false" not in (debug_session.path / "preset.dstack.yml").read_text()

    @pytest.mark.parametrize("status", ["success", "failed"])
    def test_finish_records_terminal_status(self, tmp_path, monkeypatch, status):
        self._home(tmp_path, monkeypatch)
        session = create_preset_agent_session(self._configuration())

        finished_path = session.finish(status)

        assert finished_path == session.path
        assert json.loads((session.path / "session.json").read_text())["status"] == status

    def test_finish_writes_status_in_place(self, tmp_path):
        session_dir = tmp_path / "20260714-120000-000000Z"
        session_dir.mkdir()
        (session_dir / "agent.log").touch()
        session = PresetAgentSession(
            path=session_dir,
            debug=False,
        )

        path = session.finish("failed")

        assert path == session_dir
        assert json.loads((session_dir / "session.json").read_text()) == {"status": "failed"}

    def test_reports_invalid_existing_parent(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        (tmp_path / ".dstack").mkdir(parents=True)
        (tmp_path / ".dstack" / "presets").write_text("not a directory")

        with pytest.raises(CLIError, match="Could not create agent output"):
            create_preset_agent_session(
                PresetConfiguration(name="qwen", model={"base": "Qwen/Qwen3.5-27B"})
            )

    def test_log_write_failure_warns_once(self, tmp_path, capsys):
        path = tmp_path / "agent-running"
        path.mkdir()
        (path / "agent.log").touch()
        session = PresetAgentSession(
            path=path,
            debug=False,
        )
        shutil.rmtree(path)

        session.append_log("first")
        session.append_log("second")

        assert capsys.readouterr().out.count("Could not write agent log") == 1


class TestRedaction:
    def test_does_not_replace_short_values_inside_diagnostics(self):
        assert redact("DEBUG=1; enabled=false", ("1", "false")) == "DEBUG=1; enabled=false"
        assert redact("false", ("false",)) == "[redacted]"
        assert redact("token=secret-token", ("secret-token",)) == "token=[redacted]"


class TestAgentOutput:
    @pytest.mark.asyncio
    async def test_sends_prompt_and_redacts_raw_output(self, tmp_path, monkeypatch, capsys):
        script = tmp_path / "fake_claude.py"
        script.write_text(
            """import json
import sys

prompt = sys.stdin.read()
print(json.dumps({
    "type": "result",
    "is_error": True,
    "result": "bad secret-token",
    "secret-token": "must be redacted",
    "structured_output": {"prompt": prompt},
}))
"""
        )
        (tmp_path / "progress.jsonl").touch()
        monkeypatch.setattr(
            "dstack._internal.cli.services.presets.agent._build_claude_command",
            lambda **_: [sys.executable, str(script)],
        )

        workspace = PresetAgentWorkspace(path=tmp_path, dstack_home=tmp_path / "home")
        session_path = tmp_path / "debug-running"
        session_path.mkdir()
        (session_path / "agent.log").touch()
        (session_path / "trace.jsonl").touch()
        agent_session = PresetAgentSession(
            path=session_path,
            debug=True,
        )
        output = await run_preset_agent(
            prompt="full preset prompt",
            env=os.environ.copy(),
            workspace=workspace,
            auth=_claude_auth(),
            redacted_values=("secret-token",),
            agent_session=agent_session,
        )

        assert output.report_data == {"prompt": "full preset prompt"}
        assert output.error == "bad [redacted]"
        trace = [json.loads(line) for line in agent_session.trace_path.read_text().splitlines()]
        assert len(trace) == 1
        assert trace[0]["timestamp"].endswith("Z")
        assert trace[0]["stream"] == "stdout"
        assert trace[0]["event"]["result"] == "bad [redacted]"
        assert "[redacted]" in trace[0]["event"]
        assert capsys.readouterr().out == ""

    @pytest.mark.asyncio
    async def test_accepts_stream_event_larger_than_64_kib(self, tmp_path, monkeypatch):
        script = tmp_path / "fake_claude.py"
        script.write_text(
            """import json

print(json.dumps({
    "type": "result",
    "structured_output": {"value": "x" * (128 * 1024)},
}))
"""
        )
        (tmp_path / "progress.jsonl").touch()
        session_path = tmp_path / "agent-running"
        session_path.mkdir()
        (session_path / "agent.log").touch()
        monkeypatch.setattr(
            "dstack._internal.cli.services.presets.agent._build_claude_command",
            lambda **_: [sys.executable, str(script)],
        )

        output = await run_preset_agent(
            prompt="prompt",
            env=os.environ.copy(),
            workspace=PresetAgentWorkspace(path=tmp_path, dstack_home=tmp_path / "home"),
            auth=_claude_auth(),
            redacted_values=(),
            agent_session=PresetAgentSession(
                path=session_path,
                debug=False,
            ),
        )

        assert output.report_data is not None
        assert len(output.report_data["value"]) == 128 * 1024

    def test_progress_stream_prints_only_redacted_messages(self, tmp_path, capsys):
        progress_path = tmp_path / "progress.jsonl"
        progress_path.write_text('{"message":"using secret-token"}\n')
        session_path = tmp_path / "agent-running"
        session_path.mkdir()
        (session_path / "agent.log").touch()
        agent_session = PresetAgentSession(
            path=session_path,
            debug=False,
        )

        _ProgressTailer(
            path=progress_path,
            redacted_values=("secret-token",),
            agent_session=agent_session,
        ).flush()

        output = capsys.readouterr().out
        assert "using [redacted]" in output
        assert "secret-token" not in output
        log = agent_session.log_path.read_text()
        assert "using [redacted]" in log
        assert "secret-token" not in log


class TestProcessCleanup:
    @pytest.mark.windows_only
    @pytest.mark.asyncio
    async def test_terminates_windows_process_tree(self):
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            (
                "import subprocess,sys,time; "
                "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
                "print(p.pid,flush=True); time.sleep(60)"
            ),
            stdout=asyncio.subprocess.PIPE,
        )
        assert proc.stdout is not None
        child_pid = int((await proc.stdout.readline()).decode())

        await _terminate_process(proc)

        assert proc.returncode is not None
        assert not psutil.pid_exists(child_pid)


class TestRecordMirror:
    def test_mirrors_complete_lines_redacted(self, tmp_path):
        source = tmp_path / "runs.jsonl"
        target = tmp_path / "mirror" / "runs.jsonl"
        target.parent.mkdir()
        mirror = _RecordMirror(source=source, target=target, redacted_values=["dstack-secret"])

        source.write_text(
            '{"name":"run-1","note":"dstack-secret"}\n{"name":"run-2"', encoding="utf-8"
        )
        mirror.flush()

        assert target.read_text() == '{"name":"run-1","note":"[redacted]"}\n'

        with source.open("a", encoding="utf-8") as f:
            f.write("}\n")
        mirror.flush()

        assert target.read_text().splitlines() == [
            '{"name":"run-1","note":"[redacted]"}',
            '{"name":"run-2"}',
        ]

    def test_missing_source_is_no_op(self, tmp_path):
        mirror = _RecordMirror(
            source=tmp_path / "absent.jsonl",
            target=tmp_path / "target.jsonl",
            redacted_values=[],
        )

        mirror.flush()

        assert not (tmp_path / "target.jsonl").exists()


class TestWriteAgentInfo:
    def test_writes_model_params_and_auth(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "dstack._internal.cli.services.presets.agent._get_claude_version",
            lambda auth: "2.1.0 (Claude Code)",
        )
        monkeypatch.setattr(
            "dstack._internal.cli.services.presets.agent._get_claude_auth_status",
            lambda auth: {"authMethod": "claude.ai", "loggedIn": True},
        )
        session_dir = tmp_path / "session"
        session_dir.mkdir()
        session = PresetAgentSession(path=session_dir, debug=True)

        session.write_agent_info(
            ClaudeAuth(api_key=None, executable="claude", effort=None, model="claude-opus-4-8")
        )

        assert json.loads((session_dir / "agent.json").read_text()) == {
            "executable": "claude",
            "version": "2.1.0 (Claude Code)",
            "model": {"name": "claude-opus-4-8", "effort": "default"},
            "auth": {"authMethod": "claude.ai", "loggedIn": True},
        }


def _subprocess_env() -> dict[str, str]:
    # A minimal realistic agent env: build_preset_agent_env never produces an
    # empty dict, and env={} crashes CreateProcess on Windows 3.10, which lacks
    # the cpython gh-105436 fix.
    names = ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "COMSPEC", "TEMP", "TMP")
    return {name: value for name in names if (value := os.environ.get(name))}


def _write_fake_claude(tmp_path, script_body: str) -> Path:
    script = tmp_path / "fake_claude.py"
    script.write_text(script_body)
    return script


def _agent_setup(tmp_path):
    (tmp_path / "progress.jsonl").touch()
    workspace = PresetAgentWorkspace(path=tmp_path, dstack_home=tmp_path / "home")
    session_path = tmp_path / "session"
    session_path.mkdir()
    (session_path / "agent.log").touch()
    agent_session = PresetAgentSession(
        path=session_path,
        debug=False,
    )
    return workspace, agent_session


def _patch_claude_command(monkeypatch, script):
    monkeypatch.setattr(
        "dstack._internal.cli.services.presets.agent._build_claude_command",
        lambda **kwargs: [sys.executable, str(script)]
        + (["--resume", kwargs["resume_session_id"]] if kwargs.get("resume_session_id") else []),
    )


class TestConnectionResume:
    @pytest.mark.asyncio
    async def test_resumes_after_connection_error(self, tmp_path, monkeypatch, capsys):
        script = _write_fake_claude(
            tmp_path,
            """import json
import sys
from pathlib import Path

args = sys.argv[1:]
with Path("calls.jsonl").open("a") as f:
    f.write(json.dumps({"args": args, "prompt": sys.stdin.read()}) + "\\n")
if "--resume" in args:
    print(json.dumps({
        "type": "result",
        "session_id": "sid-123",
        "structured_output": {"resumed": True},
    }))
else:
    print(json.dumps({"type": "system", "subtype": "init", "session_id": "sid-123"}))
    print(json.dumps({
        "type": "result",
        "is_error": True,
        "result": "API Error: Unable to connect to API (ENOTFOUND)",
    }))
    sys.exit(1)
""",
        )
        monkeypatch.setattr(
            "dstack._internal.cli.services.presets.agent._RESUME_DELAYS_SECONDS", (0,)
        )
        _patch_claude_command(monkeypatch, script)
        workspace, agent_session = _agent_setup(tmp_path)

        output = await run_preset_agent(
            prompt="system prompt",
            env=_subprocess_env(),
            workspace=workspace,
            auth=ClaudeAuth(api_key=None, executable="claude", effort=None, model="m"),
            redacted_values=(),
            agent_session=agent_session,
        )

        assert output.report_data == {"resumed": True}
        calls = [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()]
        assert len(calls) == 2
        assert calls[0]["args"] == []
        assert calls[0]["prompt"] == "system prompt"
        assert calls[1]["args"] == ["--resume", "sid-123"]
        assert "The previous agent process was interrupted" in calls[1]["prompt"]
        assert "resuming" in capsys.readouterr().out

    @pytest.mark.asyncio
    async def test_resumes_on_any_unreported_death(self, tmp_path, monkeypatch):
        script = _write_fake_claude(
            tmp_path,
            """import json
import sys
from pathlib import Path

with Path("calls.jsonl").open("a") as f:
    f.write("call\\n")
if "--resume" in sys.argv[1:]:
    print(json.dumps({"type": "result", "structured_output": {"recovered": True}}))
else:
    print(json.dumps({"type": "system", "subtype": "init", "session_id": "sid-123"}))
    print(json.dumps({"type": "result", "is_error": True, "result": "model refused"}))
    sys.exit(1)
""",
        )
        monkeypatch.setattr(
            "dstack._internal.cli.services.presets.agent._RESUME_DELAYS_SECONDS", (0,)
        )
        _patch_claude_command(monkeypatch, script)
        workspace, agent_session = _agent_setup(tmp_path)

        output = await run_preset_agent(
            prompt="system prompt",
            env=_subprocess_env(),
            workspace=workspace,
            auth=ClaudeAuth(api_key=None, executable="claude", effort=None, model="m"),
            redacted_values=(),
            agent_session=agent_session,
        )

        assert output.report_data == {"recovered": True}
        assert len((tmp_path / "calls.jsonl").read_text().splitlines()) == 2


class TestConnectionRetryExhaustion:
    @pytest.mark.asyncio
    async def test_gives_up_after_repeated_no_progress_failures(self, tmp_path, monkeypatch):
        script = _write_fake_claude(
            tmp_path,
            """import json
import sys
from pathlib import Path

with Path("calls.jsonl").open("a") as f:
    f.write("call\\n")
print(json.dumps({"type": "system", "subtype": "init", "session_id": "sid-123"}))
print(json.dumps({
    "type": "result",
    "is_error": True,
    "result": "API Error: Unable to connect to API (ENOTFOUND)",
}))
sys.exit(1)
""",
        )
        monkeypatch.setattr(
            "dstack._internal.cli.services.presets.agent._RESUME_DELAYS_SECONDS", (0, 0)
        )
        _patch_claude_command(monkeypatch, script)
        workspace, agent_session = _agent_setup(tmp_path)

        output = await run_preset_agent(
            prompt="system prompt",
            env=_subprocess_env(),
            workspace=workspace,
            auth=ClaudeAuth(api_key=None, executable="claude", effort=None, model="m"),
            redacted_values=(),
            agent_session=agent_session,
        )

        assert output.report_data is None
        assert output.error is not None and "Unable to connect" in output.error
        # Initial attempt + one retry per configured delay, then give up.
        assert len((tmp_path / "calls.jsonl").read_text().splitlines()) == 3


class TestWorkspaceLifecycle:
    def _session(self, tmp_path):
        session_dir = tmp_path / "sessions" / "ab12cd34"
        session_dir.mkdir(parents=True)
        return PresetAgentSession(path=session_dir, debug=False, preset_id="ab12cd34")

    @pytest.mark.skipif(IS_WINDOWS, reason="workspace alias symlinks are POSIX-only")
    def test_create_attach_and_remove(self, tmp_path):
        session = self._session(tmp_path)

        workspace = create_agent_workspace(session)
        manifest = session.read_manifest()
        alias = Path(manifest["alias"])
        assert Path(manifest["workspace"]) == session.path / "workspace"
        assert alias.is_symlink()
        (workspace.path / "note.txt").write_text("kept", encoding="utf-8")

        os.unlink(alias)
        attached = attach_agent_workspace(session)
        assert alias.is_symlink()
        assert (attached.path / "note.txt").read_text() == "kept"

        remove_agent_workspace(session)
        assert not os.path.lexists(alias)
        assert not (session.path / "workspace").exists()

    @pytest.mark.skipif(IS_WINDOWS, reason="workspace alias symlinks are POSIX-only")
    def test_attach_refuses_occupied_alias(self, tmp_path):
        session = self._session(tmp_path)
        create_agent_workspace(session)
        manifest = session.read_manifest()
        alias = Path(manifest["alias"])
        os.unlink(alias)
        alias.mkdir()
        try:
            with pytest.raises(CLIError, match="cannot be used safely"):
                attach_agent_workspace(session)
        finally:
            alias.rmdir()

    def test_attach_fails_when_workspace_is_gone(self, tmp_path):
        session = self._session(tmp_path)
        create_agent_workspace(session)
        remove_agent_workspace(session)
        with pytest.raises(CLIError, match="no longer exists"):
            attach_agent_workspace(session)


class TestOffsetPersistence:
    def test_mirror_does_not_duplicate_after_restart(self, tmp_path):
        from dstack._internal.cli.services.presets.tail import _OffsetStore

        source = tmp_path / "runs.jsonl"
        target = tmp_path / "mirror.jsonl"
        state = tmp_path / ".offsets.json"
        source.write_text('{"name":"one"}\n', encoding="utf-8")

        mirror = _RecordMirror(
            source=source,
            target=target,
            redacted_values=(),
            offset_store=_OffsetStore(state),
            offset_key="runs",
        )
        mirror.flush()

        with source.open("a", encoding="utf-8") as f:
            f.write('{"name":"two"}\n')
        restarted = _RecordMirror(
            source=source,
            target=target,
            redacted_values=(),
            offset_store=_OffsetStore(state),
            offset_key="runs",
        )
        restarted.flush()

        assert target.read_text().splitlines() == ['{"name":"one"}', '{"name":"two"}']


class TestLoadResumableSession:
    def _write_session(self, tmp_path, monkeypatch, manifest):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        path = tmp_path / ".dstack" / "presets" / manifest["id"]
        path.mkdir(parents=True)
        (path / "session.json").write_text(json.dumps(manifest), encoding="utf-8")
        return path

    def test_loads_interrupted_session(self, tmp_path, monkeypatch):
        self._write_session(
            tmp_path,
            monkeypatch,
            {
                "id": "ab12cd34",
                "status": "interrupted",
                "claude_session_id": "sid-1",
                "debug": True,
                "created_at": "2026-07-20T10:00:00+00:00",
            },
        )

        session = load_resumable_agent_session("ab12cd34")

        assert session.preset_id == "ab12cd34"
        assert session.debug is True

    def test_treats_dead_running_session_as_resumable(self, tmp_path, monkeypatch):
        self._write_session(
            tmp_path,
            monkeypatch,
            {
                "id": "ab12cd34",
                "status": "running",
                "pid": 4242,
                "claude_session_id": "sid-1",
            },
        )
        monkeypatch.setattr(
            "dstack._internal.cli.services.presets.session.psutil.pid_exists",
            lambda pid: False,
        )

        assert load_resumable_agent_session("ab12cd34").preset_id == "ab12cd34"

    @pytest.mark.parametrize(
        ("manifest", "match"),
        [
            pytest.param(None, "Unknown preset", id="unknown-preset"),
            pytest.param(
                {"id": "aa000001", "status": "success"}, "nothing to resume", id="success"
            ),
            pytest.param({"id": "aa000002", "status": "failed"}, "cannot be resumed", id="failed"),
            pytest.param(
                {
                    "id": "aa000003",
                    "status": "running",
                    "pid": 4242,
                    "claude_session_id": "sid-1",
                },
                "still being created",
                id="still-running",
            ),
            pytest.param(
                {"id": "aa000004", "status": "interrupted"},
                "stopped before it started",
                id="interrupted-before-start",
            ),
        ],
    )
    def test_refusals(self, tmp_path, monkeypatch, manifest, match):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        if manifest is not None:
            self._write_session(tmp_path, monkeypatch, manifest)
        monkeypatch.setattr(
            "dstack._internal.cli.services.presets.session.psutil.pid_exists",
            lambda pid: True,
        )
        preset_id = manifest["id"] if manifest is not None else "00000000"

        with pytest.raises(CLIError, match=match):
            load_resumable_agent_session(preset_id)


class TestSummarizeSessionTrials:
    def test_counts_records_even_when_trials_share_a_task(self, tmp_path):
        record = {
            "task": {"name": "qwen-ab12cd34-1"},
            "resources": {"gpu": {"name": "A40", "memory": "48GB", "count": 1}},
            "benchmark": {
                "workload": {"concurrency": 8},
                "metrics": {"duration_seconds": 10.0, "total_output_tokens": 20000},
            },
        }
        rerun = json.loads(json.dumps(record))
        rerun["benchmark"]["metrics"]["total_output_tokens"] = 23000
        second_trial = json.loads(json.dumps(record))
        second_trial["task"]["name"] = "qwen-ab12cd34-2"
        nameless = {"benchmark": {"workload": {}, "metrics": {}}}
        path = tmp_path / "trials.jsonl"
        path.write_text(
            "\n".join(json.dumps(entry) for entry in [record, rerun, second_trial, nameless])
        )

        summary = _summarize_session_trials(path)

        # 4 records = 4 trials: one long-lived task commonly hosts several
        # trials, so shared task names must not collapse the count.
        assert summary["count"] == 4
        assert summary["best"] == {"tok_s": 2300.0, "concurrency": 8, "gpu": "A40:48GB:1"}


class TestFileLineReader:
    @pytest.mark.asyncio
    async def test_reads_lines_and_continues_from_persisted_offset(self, tmp_path):
        from dstack._internal.cli.services.presets.tail import _FileLineReader, _OffsetStore

        stream = tmp_path / "stdout.jsonl"
        state = tmp_path / ".offsets.json"
        stream.write_bytes(b"first\nsecond\n")
        alive = True

        reader = _FileLineReader(
            stream,
            offset_store=_OffsetStore(state),
            offset_key="agent_stdout",
            is_alive=lambda: alive,
        )
        assert await reader.readline() == b"first\n"
        assert await reader.readline() == b"second\n"

        # A new reader (a later attach) continues where the previous stopped.
        with stream.open("ab") as f:
            f.write(b"third\npartial")
        alive = False
        attached = _FileLineReader(
            stream,
            offset_store=_OffsetStore(state),
            offset_key="agent_stdout",
            is_alive=lambda: alive,
        )
        assert await attached.readline() == b"third\n"
        assert await attached.readline() == b"partial"
        assert await attached.readline() == b""


class TestStopOrDetach:
    @pytest.mark.skipif(IS_WINDOWS, reason="exercises POSIX process groups")
    def test_detach_keeps_the_agent_and_stop_terminates_it(self, tmp_path, monkeypatch, capsys):
        from dstack._internal.cli.services.presets import create as create_module
        from dstack._internal.cli.services.presets.create import _stop_or_detach_agent_session

        session_dir = tmp_path / "ab12cd34"
        session_dir.mkdir()
        (session_dir / "agent.log").touch()
        session = PresetAgentSession(path=session_dir, debug=False, preset_id="ab12cd34")
        agent = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(300)"], start_new_session=True
        )
        try:
            session.update_manifest(status="running", agent_pid=agent.pid)

            monkeypatch.setattr(create_module, "confirm_ask", lambda *_: False)
            _stop_or_detach_agent_session(session)
            assert agent.poll() is None
            assert session.read_manifest()["status"] == "running"
            assert "Detached" in capsys.readouterr().out

            monkeypatch.setattr(create_module, "confirm_ask", lambda *_: True)
            _stop_or_detach_agent_session(session)
            psutil.Process(agent.pid).wait(timeout=10)
            assert session.read_manifest()["status"] == "interrupted"
        finally:
            with suppress(OSError):
                os.killpg(agent.pid, signal.SIGKILL)


class TestOffsetStoreSharing:
    def test_shared_store_keeps_every_writers_keys(self, tmp_path):
        import threading

        from dstack._internal.cli.services.presets.tail import _OffsetStore

        state = tmp_path / ".offsets.json"
        store = _OffsetStore(state)

        # One store serves the whole session; readers and mirrors write
        # disjoint keys from worker threads.
        def advance(key: str) -> None:
            for offset in range(1, 51):
                store.set(key, offset)

        threads = [
            threading.Thread(target=advance, args=(key,))
            for key in ("agent_stdout", "agent_stderr", "runs", "trials")
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        reloaded = _OffsetStore(state)
        for key in ("agent_stdout", "agent_stderr", "runs", "trials"):
            assert reloaded.get(key) == 50
