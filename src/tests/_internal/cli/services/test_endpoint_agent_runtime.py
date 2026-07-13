import asyncio
import os
import shutil
import subprocess
import sys
from types import SimpleNamespace

import psutil
import pytest

from dstack._internal.cli.services.endpoint_agent_runtime import (
    ClaudeAuth,
    EndpointAgentWorkspace,
    _build_claude_command,
    _prepare_subprocess_command,
    _ProgressTailer,
    _terminate_process,
    build_endpoint_agent_env,
    contains_redacted_value,
    endpoint_agent_workspace,
    get_claude_auth,
    run_endpoint_agent,
)
from dstack._internal.compat import IS_WINDOWS
from dstack._internal.core.errors import CLIError

pytestmark = pytest.mark.windows


def _claude_auth(*, use_existing: bool = False, effort=None) -> ClaudeAuth:
    return ClaudeAuth(
        api_key=None if use_existing else "anthropic-secret",
        executable="claude",
        effort=effort,
        model="claude-test",
        use_existing=use_existing,
    )


class TestClaudeAuth:
    def test_rejects_api_key_and_existing_auth_together(self, monkeypatch):
        monkeypatch.setenv("DSTACK_AGENT_ANTHROPIC_API_KEY", "key")
        monkeypatch.setenv("DSTACK_AGENT_CLAUDE_USE_EXISTING_AUTH", "1")

        with pytest.raises(CLIError, match="cannot both be set"):
            get_claude_auth()

    def test_requires_an_auth_mode(self, monkeypatch):
        monkeypatch.delenv("DSTACK_AGENT_ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("DSTACK_AGENT_CLAUDE_USE_EXISTING_AUTH", raising=False)

        with pytest.raises(CLIError, match="DSTACK_AGENT_ANTHROPIC_API_KEY is not set"):
            get_claude_auth()

    @pytest.mark.parametrize("use_existing", [False, True])
    def test_builds_command_for_selected_auth_mode(self, use_existing):
        command = _build_claude_command(
            auth=_claude_auth(use_existing=use_existing, effort="high")
        )

        assert ("--bare" in command) is not use_existing
        assert ("--setting-sources" in command) is use_existing
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

        env = build_endpoint_agent_env(
            api=api,
            endpoint_env={"HF_TOKEN": "hf-secret"},
            auth=_claude_auth(),
            workspace=EndpointAgentWorkspace(
                path=tmp_path,
                dstack_home=tmp_path / "home",
            ),
            token="dstack-secret",
        )

        assert env["DSTACK_SERVER_URL"] == "http://127.0.0.1:3000"
        assert env["DSTACK_PROJECT"] == "main"
        assert env["DSTACK_TOKEN"] == "dstack-secret"
        assert env["HF_TOKEN"] == "hf-secret"
        assert "UNRELATED_SECRET" not in env

    def test_creates_private_cli_home_and_dstack_wrapper(self):
        with endpoint_agent_workspace() as workspace:
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

    def test_keeps_control_socket_path_bounded(self):
        with endpoint_agent_workspace() as workspace:
            if not IS_WINDOWS:
                socket_path = (
                    workspace.dstack_home / ".dstack" / "ssh" / f"{'x' * 41}.control.sock"
                )
                assert len(os.fsencode(socket_path)) <= 103

    def test_detects_known_secret_in_generated_artifact(self):
        assert contains_redacted_value(
            {"commands": ["serve --token secret-token"]},
            ("secret-token",),
        )


class TestAgentOutput:
    @pytest.mark.asyncio
    async def test_sends_prompt_and_redacts_raw_output(self, tmp_path, monkeypatch):
        script = tmp_path / "fake_claude.py"
        script.write_text(
            """import json
import sys

prompt = sys.stdin.read()
print(json.dumps({
    "type": "result",
    "is_error": True,
    "result": "bad secret-token",
    "structured_output": {"prompt": prompt},
}))
"""
        )
        (tmp_path / "progress.jsonl").touch()
        monkeypatch.setattr(
            "dstack._internal.cli.services.endpoint_agent_runtime._build_claude_command",
            lambda **_: [sys.executable, str(script)],
        )

        workspace = EndpointAgentWorkspace(path=tmp_path, dstack_home=tmp_path / "home")
        output = await run_endpoint_agent(
            prompt="full endpoint prompt",
            env=os.environ.copy(),
            workspace=workspace,
            auth=_claude_auth(),
            redacted_values=("secret-token",),
        )

        assert output.report_data == {"prompt": "full endpoint prompt"}
        assert output.error == "bad [redacted]"
        assert "secret-token" not in workspace.stdout_path.read_text()

    def test_progress_stream_prints_only_redacted_messages(self, tmp_path, capsys):
        progress_path = tmp_path / "progress.jsonl"
        progress_path.write_text('{"message":"using secret-token"}\n')

        _ProgressTailer(path=progress_path, redacted_values=("secret-token",)).flush()

        output = capsys.readouterr().out
        assert "using [redacted]" in output
        assert "secret-token" not in output


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
