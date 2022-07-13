from argparse import Namespace
from getpass import getpass
from typing import Optional


def confirm(message: str) -> bool:
    reply = None
    while reply != "y" and reply != "n":
        reply = input(f"{message} [y/n]? ").lower().rstrip()
    return reply == "y"


def get_or_ask(args: Namespace, obj: Optional[object], field: str, prompt: str, secure: bool,
               required: bool = True) -> Optional[str]:
    old_value = getattr(obj, field) if obj is not None else None
    obj = getattr(args, field)
    if obj is None:
        value = None
        while value is None:
            value = getpass(prompt) if secure else input(prompt)
            value = value if value.strip() != "" else old_value
            if value is None and not required:
                break
        return value
    else:
        return obj
