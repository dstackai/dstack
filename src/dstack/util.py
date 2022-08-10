from typing import Optional


def _quoted(s: Optional[str]) -> str:
    if s:
        return f"\"{s}\""
    else:
        return "None"
