import os
from dataclasses import dataclass
from pathlib import Path, PurePath, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Optional, Union

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


def is_absolute_posix_path(path: PathLike) -> bool:
    # Passing Windows path leads to undefined behavior
    if str(path).startswith("~"):
        return True
    return PurePosixPath(path).is_absolute()


def make_tmp_symlink_to_dir(
    dirpath: PathLike, symlink_dirname: str, base_dir: Optional[PathLike] = None
) -> tuple[TemporaryDirectory, Path]:
    temp_dir = TemporaryDirectory(dir=base_dir)
    symlink_dir = Path(temp_dir.name) / symlink_dirname
    symlink_dir.symlink_to(dirpath, target_is_directory=True)
    return temp_dir, symlink_dir
