import re
from pathlib import Path
from typing import Optional

from dstack._internal.core.errors import CLIError

_SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent / "resources" / "system_prompt.md"

# `<!--?NAME:CONTENT-->` emits CONTENT (with `{NAME}` interpolated) when the
# variable NAME is set, and nothing otherwise. The conditional text lives in
# the document; this module only applies the rule.
_DIRECTIVE_PATTERN = re.compile(r"<!--\?(\w+):(.*?)-->", re.DOTALL)

# `<!--!NOTE-->` is a note for maintainers and is dropped before the agent sees
# the document. Any other comment is left alone, so that a plain `<!-- -->` or a
# malformed directive stays visible instead of disappearing silently.
_NOTE_PATTERN = re.compile(r"<!--!.*?-->\n?", re.DOTALL)


# TODO: reintroduce a `# Resume` section in system_prompt.md once session resume
# (seeded from `runs.jsonl` and the trial records) is designed.
def get_preset_agent_system_prompt(
    user_prompt: Optional[str] = None,
    baseline: bool = False,
) -> str:
    text = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    variables = {
        "prompt": user_prompt.strip() if user_prompt else None,
        # Rendered for its presence only; the directive body must not interpolate it.
        "baseline": "on" if baseline else None,
    }
    applied: set[str] = set()

    def substitute(match: re.Match) -> str:
        name, content = match.group(1), match.group(2)
        if name not in variables:
            raise CLIError(f"Unknown variable {name!r} in the agent system prompt")
        value = variables[name]
        if not value:
            return ""
        applied.add(name)
        return content.replace("{" + name + "}", value)

    rendered = _NOTE_PATTERN.sub("", _DIRECTIVE_PATTERN.sub(substitute, text))
    if variables["prompt"] and "prompt" not in applied:
        raise CLIError("The agent system prompt has no place for the user prompt")
    for name, value in variables.items():
        if value and name not in applied:
            raise CLIError(f"The agent system prompt has no place for {name!r}")
    return re.sub(r"\n{3,}", "\n\n", rendered)
