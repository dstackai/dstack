from argparse import Namespace
from typing import Optional, Any

from rich.prompt import Prompt


def get_or_ask(args: Namespace, obj: Optional[object], field: str, prompt: str, secure: bool,
               required: bool = True, default: Optional[Any] = None) -> Optional[str]:
    old_value = getattr(obj, field) if obj is not None else None
    obj = getattr(args, field)
    if obj is None:
        value = None
        while value is None:
            value = Prompt.ask(prompt, password=True) if secure else Prompt.ask(prompt, default=default)
            value = value if value.strip() != "" else old_value
            if value is None and not required:
                break
        return value
    else:
        return obj
