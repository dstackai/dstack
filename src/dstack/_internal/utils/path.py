import os
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Union

PathLike = Union[str, os.PathLike]


@dataclass
class FilePath:
    path: PathLike


@dataclass
class FileContent:
    content: str


FilePathOrContent = Union[FilePath, FileContent]


def path_in_dir(path: PathLike, directory: PathLike) -> bool:
    try:
        Path(path).resolve().relative_to(Path(directory).resolve())
        return True
    except ValueError:
        return False


def normalize_path(path: PathLike) -> PurePath:
    path = PurePath(path)
    stack = []
    for part in path.parts:
        if part == "..":
            if not stack:
                raise ValueError("Path is outside of the top directory")
            stack.pop()
        else:
            stack.append(part)
    return PurePath(*stack)


def resolve_relative_path(path: PathLike) -> PurePath:
    path = PurePath(path)
    if path.is_absolute():
        raise ValueError("Path should be relative")
    try:
        return normalize_path(path)
    except ValueError:
        raise ValueError("Path is outside of the repo")
