from pathlib import Path
from typing import Optional

from dstack._internal.core.errors import CLIError

DEFAULT_SKILL_RELATIVE_PATH = Path("skills/dstack/SKILL.md")


def find_skill_path(skill_path: Optional[str] = None) -> Path:
    if skill_path is not None:
        path = Path(skill_path)
        if not path.is_file():
            raise CLIError(f"Skill file not found: {skill_path}")
        return path

    candidates = [
        Path.cwd() / DEFAULT_SKILL_RELATIVE_PATH,
        Path(__file__).resolve().parents[4] / DEFAULT_SKILL_RELATIVE_PATH,
    ]
    for path in candidates:
        if path.is_file():
            return path

    raise CLIError(
        "dstack skill not found. Expected "
        f"[code]{DEFAULT_SKILL_RELATIVE_PATH}[/] in the current directory."
    )


def load_skill_content(skill_path: Optional[str] = None) -> str:
    return find_skill_path(skill_path).read_text(encoding="utf-8")
