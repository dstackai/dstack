import fnmatch
from itertools import zip_longest
from pathlib import Path
from typing import Dict, List, Optional

from dstack._internal.utils.path import PathLike


class GitIgnore:
    def __init__(
        self, root_dir: PathLike, ignore_files: List[str] = None, globs: List[str] = None
    ):
        self.root_dir = Path(root_dir)
        self.ignore_files = (
            ignore_files
            if ignore_files is not None
            else [".gitignore", ".git/info/exclude", ".dstackignore"]
        )
        self.ignore_globs: Dict[str, List[str]] = {".": globs or []}
        self.load_recursive()

    def load_ignore_file(self, path: str, ignore_file: Path):
        if path != "." and not path.startswith("./"):
            path = "./" + path
        if path not in self.ignore_globs:
            self.ignore_globs[path] = []
        with ignore_file.open("r") as f:
            for line in f:
                line = self.rstrip(line.rstrip("\n")).rstrip("/")
                line = line.replace("\\ ", " ")
                if line.startswith("#") or not line:
                    continue
                self.ignore_globs[path].append(line)

    def load_recursive(self, path: Optional[Path] = None):
        path = path or self.root_dir
        for ignore_file in self.ignore_files:
            ignore_file = path / ignore_file
            if ignore_file.exists():
                self.load_ignore_file(str(path.relative_to(self.root_dir)), ignore_file)

        for subdir in path.iterdir():
            if not subdir.is_dir() or self.ignore(subdir.relative_to(self.root_dir)):
                continue
            self.load_recursive(subdir)

    @staticmethod
    def rstrip(value: str) -> str:
        end = len(value) - 1
        while end >= 0:
            if not value[end].isspace():
                break
            if end > 0 and value[end - 1] == "\\":
                break  # escaped space
            end -= 1
        else:
            return ""
        return value[: end + 1]

    @staticmethod
    def fnmatch(name: str, pattern: str, sep="/") -> bool:
        if pattern.startswith(sep):
            name = sep + name
        for n, p in zip_longest(
            reversed(name.split(sep)), reversed(pattern.split(sep)), fillvalue=None
        ):
            if p == "**":
                raise NotImplementedError()
            if p is None:
                return True
            if n is None or not fnmatch.fnmatch(n, p):
                return False
        return True

    def ignore(self, path: PathLike, sep="/") -> bool:
        if not path:
            return False
        path = Path(path)
        if path.is_absolute():
            path = path.relative_to(self.root_dir)

        tokens = ("." + sep + str(path)).split(sep)
        for i in range(1, len(tokens)):
            parent = sep.join(tokens[:-i])
            globs = self.ignore_globs.get(parent)
            if not globs:
                continue
            name = sep.join(tokens[-i:])
            for glob in globs:
                if self.fnmatch(name, glob, sep=sep):
                    return True
        return False
