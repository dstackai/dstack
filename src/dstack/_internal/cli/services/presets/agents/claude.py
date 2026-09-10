"""Claude Code as the preset agent."""

import json
import os
from pathlib import Path
from typing import Literal, Optional, get_args

from pydantic import ValidationError

from dstack._internal.cli.models.preset_agent import (
    AnyClaudeStreamEvent,
    ClaudeResultEvent,
    PresetAgentInfo,
)
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
from dstack._internal.cli.services.presets.report_schema import get_report_json_schema
from dstack._internal.cli.services.presets.workspace import PresetAgentWorkspace
from dstack._internal.core.models.common import validate_json_extra_ignore
from dstack._internal.core.models.configurations import PresetAgentConfig, PresetAgentProvider

_CLAUDE_TOOLS = "Bash,Read,Write,Edit,WebFetch,WebSearch,StructuredOutput"
ClaudeEffort = Literal["low", "medium", "high", "xhigh", "max"]


class ClaudePresetAgent:
    provider: PresetAgentProvider = "claude"
    skills_dir = Path(".claude") / "skills"

    def get_spec(self, config: Optional[PresetAgentConfig]) -> PresetAgentSpec:
        return PresetAgentSpec(
            executable=resolve_executable("DSTACK_AGENT_CLAUDE_PATH", "claude", "Claude"),
            api_key=os.getenv("DSTACK_AGENT_ANTHROPIC_API_KEY") or None,
            model=choose_model(config, "DSTACK_AGENT_ANTHROPIC_MODEL"),
            effort=choose_effort(config, "DSTACK_AGENT_CLAUDE_EFFORT", get_args(ClaudeEffort)),
        )

    def get_info(self, spec: PresetAgentSpec) -> PresetAgentInfo:
        if spec.api_key:
            auth_status = "api-key"
        else:
            auth_status = probe_cli([spec.executable, "auth", "status", "--json"]) or "unknown"
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
        # With our own API key, a blank home keeps claude out of the user's `~/.claude`;
        # otherwise the user's home, so claude reuses their login.
        if spec.api_key is not None:
            env["ANTHROPIC_API_KEY"] = spec.api_key
            set_home(env, workspace.dstack_home)
        else:
            set_home(env, Path.home())

    def build_command(
        self,
        spec: PresetAgentSpec,
        workspace: PresetAgentWorkspace,
        resume_session_id: Optional[str],
    ) -> list[str]:
        command = [
            spec.executable,
            "-p",
            "--output-format",
            "stream-json",
            "--verbose",
            "--tools",
            _CLAUDE_TOOLS,
            "--allowedTools",
            _CLAUDE_TOOLS,
            "--disallowedTools",
            "Task,NotebookEdit",
            "--permission-mode",
            "bypassPermissions",
            "--json-schema",
            json.dumps(get_report_json_schema()),
        ]
        if spec.api_key is None:
            command[2:2] = ["--setting-sources", "project,local"]
        else:
            command[2:2] = ["--bare"]
        if spec.effort is not None:
            command[2:2] = ["--effort", spec.effort]
        if spec.model is not None:
            command[2:2] = ["--model", spec.model]
        if resume_session_id is not None:
            command += ["--resume", resume_session_id]
        return command

    def parse_line(self, text: str) -> Optional[PresetAgentStreamUpdate]:
        try:
            event = validate_json_extra_ignore(AnyClaudeStreamEvent, text)
        except ValidationError:
            return None
        update = PresetAgentStreamUpdate(
            session_id=event.session_id or None, model=event.model or None
        )
        if event.type == "assistant":
            update.made_progress = True
        if not isinstance(event, ClaudeResultEvent):
            return update
        if event.is_error:
            update.error = str(event.result or "Claude failed")
        if event.structured_output is not None:
            update.report_data = event.structured_output
        elif isinstance(event.result, str):
            # An agent may print the report as its final text instead of submitting
            # it through `StructuredOutput`.
            update.report_data = parse_json_object(event.result)
        return update
