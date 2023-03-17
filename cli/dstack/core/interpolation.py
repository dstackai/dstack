import string
from typing import Iterable, List, Optional

var_characters = set(string.digits + string.ascii_letters + "_")
after_dollar = var_characters | set("{$")


def validate(s: str, available_vars: Optional[Iterable[str]] = None) -> List[str]:
    """
    Validate if string could be interpolated. Supported syntax:
    * $VAR_NAME
    * ${VAR_NAME}
    * escaped $$ dollar

    Returns:
        List of missed vars
    Raises:
        ValueError: if interpolation could not be done
    """
    available_vars = set([] if available_vars is None else available_vars)
    missed_vars = set()
    start = 0
    while start < len(s):
        dollar = s.find("$", start)
        if dollar == -1:
            break
        if dollar == len(s) - 1 or (s[dollar + 1] not in after_dollar):
            raise ValueError("Unescaped $ sign")
        elif s[dollar + 1] == "$":  # escape sequence $$
            start = dollar + 2
            continue
        elif s[dollar + 1] == "{":
            end = s.find("}", dollar + 2)
            if end == -1:
                raise ValueError("Unexpected EOL")
            name = s[dollar + 2 : end].strip()
            if not all((c in var_characters) for c in name):
                raise ValueError(f"${name} contains illegal var characters")
            if name not in available_vars:
                missed_vars.add(name)
            start = end + 1
        else:
            end = dollar + 1
            while end < len(s) and s[end] in var_characters:
                end += 1
            name = s[dollar + 1 : end]
            if name not in available_vars:
                missed_vars.add(name)
            start = end
    return list(missed_vars)
