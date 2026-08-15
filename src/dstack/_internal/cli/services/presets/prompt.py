import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence, Union

from dstack._internal.core.errors import CLIError

_SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent / "resources" / "system_prompt.md"

# `<!--?if NAME-->` ... `<!--?else-->` ... `<!--?end-->` renders one branch:
# the first when the variable NAME is set (with `{NAME}` interpolated in it),
# the `else` branch (optional) otherwise. Blocks nest, and markers may sit
# inline within a line. A marker alone on its line disappears with the whole
# line, and the branch body is dedented by the indentation shared by every
# line of it; a body whose lines do not share one exact indentation is kept
# as written.
_MARKER_PATTERN = re.compile(r"<!--\?(.*?)-->")
_IF_PATTERN = re.compile(r"if\s+(\w+)")

# `<!--!NOTE-->` is a maintainer note, dropped before the agent sees the
# document. The `!` is required, so ordinary `<!-- -->` comments are preserved.
_NOTE_PATTERN = re.compile(r"<!--!.*?-->\n?", re.DOTALL)


@dataclass
class _Text:
    value: str
    at_line_start: bool


@dataclass
class _IfNode:
    name: str
    # Indents of this node's own-line markers; they sit at the enclosing
    # body's level, so the enclosing branch counts them as its lines.
    marker_indents: list[str] = field(default_factory=list)
    # An inline-opened block has no line structure of its own to dedent.
    opened_on_own_line: bool = False
    then: list[Union[_Text, "_IfNode"]] = field(default_factory=list)
    otherwise: list[Union[_Text, "_IfNode"]] = field(default_factory=list)


def _parse_directives(
    text: str, variables: dict[str, Optional[str]]
) -> list[Union[_Text, _IfNode]]:
    """Both branches are always parsed, so an unknown variable cannot hide
    behind a flag combination."""
    root: list[Union[_Text, _IfNode]] = []
    stack: list[_IfNode] = []
    in_else: list[bool] = []

    def current() -> list[Union[_Text, _IfNode]]:
        if not stack:
            return root
        return stack[-1].otherwise if in_else[-1] else stack[-1].then

    position = 0
    at_line_start = True
    for match in _MARKER_PATTERN.finditer(text):
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.end())
        line_end = len(text) if line_end == -1 else line_end
        indent = text[line_start : match.start()]
        own_line = not indent.strip() and not text[match.end() : line_end].strip()
        if own_line:
            # The marker's whole line goes away, indentation and newline included.
            run_end, next_position, next_at_line_start = (
                line_start,
                min(line_end + 1, len(text)),
                True,
            )
        else:
            run_end, next_position, next_at_line_start = match.start(), match.end(), False
        if run_end > position:
            current().append(_Text(text[position:run_end], at_line_start))
        position, at_line_start = next_position, next_at_line_start
        directive = match.group(1).strip()
        if directive == "else":
            if not stack or in_else[-1]:
                raise CLIError("`else` without a matching `if` in the agent system prompt")
            in_else[-1] = True
            if own_line:
                stack[-1].marker_indents.append(indent)
        elif directive == "end":
            if not stack:
                raise CLIError("`end` without a matching `if` in the agent system prompt")
            if own_line:
                stack[-1].marker_indents.append(indent)
            stack.pop()
            in_else.pop()
        else:
            if (if_match := _IF_PATTERN.fullmatch(directive)) is None:
                raise CLIError(f"Invalid directive {directive!r} in the agent system prompt")
            name = if_match.group(1)
            if name not in variables:
                raise CLIError(f"Unknown variable {name!r} in the agent system prompt")
            node = _IfNode(name=name, opened_on_own_line=own_line)
            if own_line:
                node.marker_indents.append(indent)
            current().append(node)
            stack.append(node)
            in_else.append(False)
    if stack:
        raise CLIError("Unclosed `if` in the agent system prompt")
    if position < len(text):
        root.append(_Text(text[position:], at_line_start))
    return root


def _branch_indent(parts: list[Union[_Text, _IfNode]]) -> str:
    """The one exact indentation shared by every line of the branch, or `""`
    when there is none. A nested block's interior belongs to that block, but
    its own-line markers sit at this branch's level and count."""
    indents = []
    for index, part in enumerate(parts):
        if isinstance(part, _IfNode):
            indents += part.marker_indents
            continue
        lines = part.value.split("\n")
        for line_index, line in enumerate(lines):
            if line_index == 0 and not part.at_line_start:
                continue  # a fragment continuing a line already counted
            is_last = line_index == len(lines) - 1
            continues_inline = (
                is_last
                and index + 1 < len(parts)
                and isinstance(parts[index + 1], _IfNode)
                and not parts[index + 1].opened_on_own_line
            )
            if line.strip():
                indents.append(line[: len(line) - len(line.lstrip())])
            elif line and continues_inline:
                # A whitespace-only fragment whose line is an inline block.
                indents.append(line)
    if indents and all(indent == indents[0] for indent in indents):
        return indents[0]
    return ""


def _render_branch(
    parts: list[Union[_Text, _IfNode]],
    variables: dict[str, Optional[str]],
    applied: set[str],
    dedent: bool,
) -> str:
    indent = _branch_indent(parts) if dedent else ""
    rendered: list[str] = []
    for part in parts:
        if isinstance(part, _Text):
            value = part.value
            if "<!--?" in value:
                raise CLIError("Malformed directive in the agent system prompt")
            if indent:
                if part.at_line_start and value.startswith(indent):
                    value = value[len(indent) :]
                value = value.replace("\n" + indent, "\n")
            rendered.append(value)
            continue
        value = variables[part.name]
        if value:
            applied.add(part.name)
            body = _render_branch(part.then, variables, applied, part.opened_on_own_line)
            rendered.append(body.replace("{" + part.name + "}", value))
        else:
            rendered.append(
                _render_branch(part.otherwise, variables, applied, part.opened_on_own_line)
            )
    return "".join(rendered)


# TODO: reintroduce a `# Resume` section in system_prompt.md once session resume
# (seeded from `runs.jsonl` and the trial records) is designed.
def get_preset_agent_system_prompt(
    user_prompt: Optional[str],
    baseline: bool,
    previous: Sequence[str],
    custom_dataset: bool,
) -> str:
    text = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    variables = {
        "prompt": user_prompt.strip() if user_prompt else None,
        # Rendered for its presence only; the directive body must not interpolate it.
        "baseline": "on" if baseline else None,
        # A comma-separated list of the previous session IDs.
        "previous": ", ".join(previous) if previous else None,
        # Rendered for its presence only; the dataset itself is in constraints.json.
        "dataset": "on" if custom_dataset else None,
    }
    applied: set[str] = set()
    rendered = _render_branch(_parse_directives(text, variables), variables, applied, dedent=False)
    rendered = _NOTE_PATTERN.sub("", rendered)
    if variables["prompt"] and "prompt" not in applied:
        raise CLIError("The agent system prompt has no place for the user prompt")
    for name, value in variables.items():
        if value and name not in applied:
            raise CLIError(f"The agent system prompt has no place for {name!r}")
    return re.sub(r"\n{3,}", "\n\n", rendered)
