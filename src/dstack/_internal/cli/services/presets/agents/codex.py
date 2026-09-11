"""OpenAI Codex CLI as the preset agent."""

import json
import os
import re
from pathlib import Path
from typing import Literal, Optional, get_args

from pydantic import ValidationError

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[import-not-found, no-redef]

from dstack._internal.cli.models.preset_agent import CodexStreamEvent, PresetAgentInfo
from dstack._internal.cli.services.presets.agents.base import (
    PresetAgentSpec,
    PresetAgentStreamUpdate,
    choose_effort,
    choose_model,
    parse_json_object,
    probe_cli,
    resolve_executable,
    set_home,
)
from dstack._internal.cli.services.presets.report_schema import get_strict_report_json_schema
from dstack._internal.cli.services.presets.workspace import PresetAgentWorkspace
from dstack._internal.core.models.common import validate_json_extra_ignore
from dstack._internal.core.models.configurations import PresetAgentConfig, PresetAgentProvider

CodexEffort = Literal["low", "medium", "high", "xhigh"]
_REPORT_SCHEMA_FILENAME = ".report-schema.json"
_LAST_MESSAGE_FILENAME = ".agent-last-message.json"
# A `-c` dotted path cannot address any other kind of table key.
_PLAIN_TOML_KEY = re.compile(r"[A-Za-z0-9_-]+")


class CodexPresetAgent:
    provider: PresetAgentProvider = "codex"
    skills_dir = Path(".codex") / "skills"

    def __init__(self) -> None:
        # Set by `build_env`; a follower that never launched codex leaves it None.
        self._codex_home: Optional[Path] = None
        self._thread_id: Optional[str] = None
        self._rollout_path: Optional[Path] = None
        # The stream never names the model; the session rollout does once the first
        # turn has started. Read on the first item and again at the end of the turn.
        self._model_reads_left = 0
        self._last_message: Optional[str] = None

    def get_spec(self, config: Optional[PresetAgentConfig]) -> PresetAgentSpec:
        return PresetAgentSpec(
            executable=resolve_executable("DSTACK_AGENT_CODEX_PATH", "codex", "Codex"),
            api_key=os.getenv("DSTACK_AGENT_OPENAI_API_KEY") or None,
            model=choose_model(config, "DSTACK_AGENT_OPENAI_MODEL"),
            effort=choose_effort(config, "DSTACK_AGENT_CODEX_EFFORT", get_args(CodexEffort)),
        )

    def get_info(self, spec: PresetAgentSpec) -> PresetAgentInfo:
        if spec.api_key:
            auth_status = "api-key"
        else:
            auth_status = (
                probe_cli([spec.executable, "login", "status"], with_stderr=True) or "unknown"
            )
        return PresetAgentInfo(
            provider=self.provider,
            executable=spec.executable,
            version=probe_cli([spec.executable, "--version"]),
            auth_status=auth_status,
            effort=spec.effort,
            model=None,
        )

    def build_env(
        self, spec: PresetAgentSpec, workspace: PresetAgentWorkspace, env: dict[str, str]
    ) -> None:
        # Like claude: with our own API key, codex runs from the workspace home with a
        # private CODEX_HOME; otherwise exactly as the user runs it.
        if spec.api_key is not None:
            env["CODEX_API_KEY"] = spec.api_key
            set_home(env, workspace.dstack_home)
            codex_home = workspace.dstack_home / ".codex"
            codex_home.mkdir(mode=0o700, exist_ok=True)
        else:
            set_home(env, Path.home())
            codex_home = get_user_codex_home()
        env["CODEX_HOME"] = str(codex_home)
        self._codex_home = codex_home
        (workspace.path / _REPORT_SCHEMA_FILENAME).write_text(
            json.dumps(get_strict_report_json_schema()), encoding="utf-8"
        )

    def build_command(
        self,
        spec: PresetAgentSpec,
        workspace: PresetAgentWorkspace,
        resume_session_id: Optional[str],
    ) -> list[str]:
        command = [spec.executable, "exec"]
        if resume_session_id is not None:
            command += ["resume", resume_session_id]
        command += [
            "--json",
            "--skip-git-repo-check",
            "--dangerously-bypass-approvals-and-sandbox",
            "--disable",
            "multi_agent",
            "--disable",
            "apps",
            "-c",
            'web_search="live"',
            "--output-schema",
            str(workspace.path / _REPORT_SCHEMA_FILENAME),
            "--output-last-message",
            str(workspace.path / _LAST_MESSAGE_FILENAME),
        ]
        if resume_session_id is None:
            # `exec resume` has no `-C`; the thread remembers its working directory.
            command += ["-C", str(workspace.path)]
        if spec.api_key is None:
            # The user's codex as they use it (auth, model provider, hooks), minus
            # their MCP servers: the agent gets no tools beyond the shell.
            command += _mcp_server_overrides(get_user_codex_home() / "config.toml")
        if spec.model is not None:
            command += ["-m", spec.model]
        if spec.effort is not None:
            command += ["-c", f'model_reasoning_effort="{spec.effort}"']
        command.append("-")
        return command

    def parse_line(self, text: str) -> Optional[PresetAgentStreamUpdate]:
        try:
            event = validate_json_extra_ignore(CodexStreamEvent, text)
        except ValidationError:
            return None
        update = PresetAgentStreamUpdate()
        if event.type == "thread.started":
            update.session_id = event.thread_id
            self._thread_id = event.thread_id
            self._model_reads_left = 2
        elif event.type == "item.completed" and event.item is not None:
            update.made_progress = True
            if event.item.type == "agent_message":
                self._last_message = event.item.text
        elif event.type == "turn.completed":
            # Only the message that ends the turn is the schema-checked report; an
            # earlier message that happens to be JSON is not.
            if self._last_message:
                update.report_data = parse_json_object(self._last_message)
        elif event.type == "turn.failed" and event.error is not None:
            update.error = event.error.message
        elif event.type == "error" and event.message:
            update.error = event.message
        if self._model_reads_left and (
            event.type.startswith("item.") or event.type == "turn.completed"
        ):
            self._model_reads_left -= 1
            update.model = self._read_rollout_model()
            if update.model is not None:
                self._model_reads_left = 0
        return update

    def _read_rollout_model(self) -> Optional[str]:
        """The `model` of the rollout's `turn_context` record, if it has been written."""
        if self._codex_home is None or self._thread_id is None:
            return None
        if self._rollout_path is None:
            pattern = f"sessions/*/*/*/rollout-*-{self._thread_id}.jsonl"
            self._rollout_path = next(iter(sorted(self._codex_home.glob(pattern))), None)
            if self._rollout_path is None:
                return None
        try:
            with self._rollout_path.open(encoding="utf-8") as rollout:
                for line in rollout:
                    record = parse_json_object(line)
                    if record is None or record.get("type") != "turn_context":
                        continue
                    payload = record.get("payload")
                    if isinstance(payload, dict) and isinstance(payload.get("model"), str):
                        return payload["model"]
        except OSError:
            return None
        return None


def get_user_codex_home() -> Path:
    return Path(os.getenv("CODEX_HOME") or Path.home() / ".codex")


def _mcp_server_overrides(config_path: Path) -> list[str]:
    """`-c` overrides that disable every MCP server in the user's config. A `-c`
    dotted path replaces the whole server table, so each gets a stub table that
    still passes codex's transport validation."""
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return []
    servers = config.get("mcp_servers")
    if not isinstance(servers, dict):
        return []
    return [
        arg
        for name in servers
        if _PLAIN_TOML_KEY.fullmatch(name)
        for arg in ("-c", f'mcp_servers.{name}={{command="disabled", enabled=false}}')
    ]
