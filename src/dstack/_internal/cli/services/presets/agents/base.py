"""The contract between the shared creation loop and one agent CLI."""

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Protocol, Sequence

from dstack._internal.cli.models.preset_agent import PresetAgentInfo
from dstack._internal.cli.services.presets.workspace import PresetAgentWorkspace
from dstack._internal.compat import IS_WINDOWS
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.configurations import PresetAgentConfig, PresetAgentProvider


@dataclass(frozen=True)
class PresetAgentSpec:
    """How the agent CLI is run: the preset's `agent` block over the
    `DSTACK_AGENT_*` variables over the CLI's own defaults."""

    executable: str
    api_key: Optional[str]
    # None means the flag is not passed and the CLI uses its own default.
    model: Optional[str]
    effort: Optional[str]


@dataclass
class PresetAgentStreamUpdate:
    """What one line of the agent's stdout contributes to the run."""

    session_id: Optional[str] = None
    model: Optional[str] = None
    made_progress: bool = False
    error: Optional[str] = None
    report_data: Optional[dict[str, Any]] = None


class PresetAgent(Protocol):
    provider: PresetAgentProvider
    # Where the CLI discovers project skills, relative to the agent's working directory.
    skills_dir: Path

    def get_spec(self, config: Optional[PresetAgentConfig]) -> PresetAgentSpec: ...

    def get_info(self, spec: PresetAgentSpec) -> PresetAgentInfo: ...

    def build_env(
        self, spec: PresetAgentSpec, workspace: PresetAgentWorkspace, env: dict[str, str]
    ) -> None:
        """Adds the CLI's own variables (auth, home) to the shared agent environment
        and puts whatever the run needs into the workspace."""
        ...

    def build_command(
        self,
        spec: PresetAgentSpec,
        workspace: PresetAgentWorkspace,
        resume_session_id: Optional[str],
    ) -> list[str]: ...

    def parse_line(self, text: str) -> Optional[PresetAgentStreamUpdate]:
        """None for a line that is not an event of this CLI."""
        ...


def resolve_executable(path_env: str, default: str, display_name: str) -> str:
    configured = os.getenv(path_env) or default
    executable = shutil.which(configured)
    if executable is None:
        raise CLIError(f"{display_name} executable not found: {configured}")
    return executable


def choose_model(config: Optional[PresetAgentConfig], env_name: str) -> Optional[str]:
    if config is not None and config.model:
        return config.model
    return os.getenv(env_name) or None


def choose_effort(
    config: Optional[PresetAgentConfig], env_name: str, allowed: Sequence[str]
) -> Optional[str]:
    """The configuration validates `agent.effort` itself; only the variable is checked here."""
    if config is not None and config.effort is not None:
        return config.effort
    effort = os.getenv(env_name) or None
    if effort is not None and effort not in allowed:
        raise CLIError(f"{env_name} must be one of: {', '.join(allowed)}")
    return effort


def set_home(env: dict[str, str], home: Path) -> None:
    env["HOME"] = str(home)
    if IS_WINDOWS:
        env["USERPROFILE"] = str(home)


def probe_cli(
    args: Sequence[str], *, env: Optional[dict[str, str]] = None, with_stderr: bool = False
) -> Optional[str]:
    """Output of a short CLI probe such as `--version`; None when it cannot run."""
    try:
        result = subprocess.run(list(args), capture_output=True, text=True, timeout=15, env=env)
    except (OSError, subprocess.SubprocessError):
        return None
    text = result.stdout + (result.stderr if with_stderr else "")
    return text.strip() or None


def parse_json_object(text: str) -> Optional[dict[str, Any]]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None
