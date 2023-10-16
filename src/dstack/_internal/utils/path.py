import os
from pathlib import Path, PurePath
from typing import Union

PathLike = Union[str, os.PathLike]


def path_in_dir(path: PathLike, directory: PathLike) -> bool:
    try:
        Path(path).resolve().relative_to(Path(directory).resolve())
        return True
    except ValueError:
        return False


def resolve_relative_path(path: str) -> PurePath:
    path = PurePath(path)
    if path.is_absolute():
        raise ValueError("Path should be relative")
    stack = []
    for part in path.parts:
        if part == "..":
            if not stack:
                raise ValueError("Path is outside of the repo")
            stack.pop()
        else:
            stack.append(part)
    return PurePath(*stack)
