"""The agent CLIs that can run a preset creation, selected by the preset's `agent.provider`
or by `DSTACK_AGENT_PROVIDER`."""

import os
from typing import Callable, Optional

from dstack._internal.cli.services.presets.agents.base import (
    PresetAgent,
    PresetAgentSpec,
    PresetAgentStreamUpdate,
)
from dstack._internal.cli.services.presets.agents.claude import ClaudePresetAgent
from dstack._internal.cli.services.presets.agents.codex import CodexPresetAgent
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.configurations import PresetAgentProvider

AGENT_PROVIDER_ENV = "DSTACK_AGENT_PROVIDER"
DEFAULT_AGENT_PROVIDER: PresetAgentProvider = "claude"
_AGENTS: dict[str, Callable[[], PresetAgent]] = {
    "claude": ClaudePresetAgent,
    "codex": CodexPresetAgent,
}


def get_preset_agent(provider: Optional[str] = None) -> PresetAgent:
    """The agent for `provider`, or for `DSTACK_AGENT_PROVIDER` (default claude) when None.
    One instance per run: an agent may keep what it learns while running."""
    if provider is None:
        provider = os.getenv(AGENT_PROVIDER_ENV) or DEFAULT_AGENT_PROVIDER
    factory = _AGENTS.get(provider)
    if factory is None:
        raise CLIError(
            f"Unknown preset agent provider {provider!r}; supported: {', '.join(_AGENTS)}"
        )
    return factory()


__all__ = [
    "AGENT_PROVIDER_ENV",
    "DEFAULT_AGENT_PROVIDER",
    "PresetAgent",
    "PresetAgentSpec",
    "PresetAgentStreamUpdate",
    "get_preset_agent",
]
