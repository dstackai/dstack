import re
from pathlib import Path
from typing import Optional

from dstack._internal.core.errors import CLIError

_SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent / "resources" / "system_prompt.md"

# `<!--?NAME:CONTENT-->` emits CONTENT (with `{NAME}` interpolated) when the
# variable NAME is set, and nothing otherwise. The conditional text lives in
# the document; this module only applies the rule.
_DIRECTIVE_PATTERN = re.compile(r"<!--\?(\w+):(.*?)-->", re.DOTALL)


# TODO: reintroduce a `# Resume` section in system_prompt.md once session resume
# (seeded from `runs.jsonl` and `trials.jsonl`) is designed.
def get_preset_agent_system_prompt(user_prompt: Optional[str] = None) -> str:
    text = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    variables = {"prompt": user_prompt.strip() if user_prompt else None}
    applied = 0

    def substitute(match: re.Match) -> str:
        nonlocal applied
        name, content = match.group(1), match.group(2)
        if name not in variables:
            raise CLIError(f"Unknown variable {name!r} in the agent system prompt")
        value = variables[name]
        if not value:
            return ""
        applied += 1
        return content.replace("{" + name + "}", value)

    rendered = _DIRECTIVE_PATTERN.sub(substitute, text)
    if variables["prompt"] and not applied:
        raise CLIError("The agent system prompt has no place for the user prompt")
    return re.sub(r"\n{3,}", "\n\n", rendered)
