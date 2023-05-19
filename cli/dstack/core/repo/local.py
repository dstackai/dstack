import fnmatch
import tarfile
from itertools import zip_longest
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional

from typing_extensions import Literal

from dstack.core.repo.base import Repo, RepoData, RepoInfo, RepoRef
from dstack.utils.common import PathLike
from dstack.utils.escape import escape_head
from dstack.utils.hash import get_sha256, slugify
from dstack.utils.workflows import load_workflows


class LocalRepoData(RepoData):
    repo_type: Literal["local"] = "local"
    repo_dir: str

    def write_code_file(self, fp: BinaryIO) -> str:
        with tarfile.TarFile(mode="w", fileobj=fp) as t:
            t.add(self.repo_dir, arcname="", filter=TarIgnore(self.repo_dir, globs=[".git"]))
        return f"code/local/{get_sha256(fp)}.tar"


class LocalRepoInfo(RepoInfo):
    repo_type: Literal["local"] = "local"
    repo_dir: str

    @property
    def head_key(self) -> str:
        repo_dir = escape_head(self.repo_dir)
        return f"{self.repo_type};{repo_dir}"


class LocalRepo(Repo):
    """Represents local folder"""

    repo_data: LocalRepoData

    def __init__(
        self,
        *,
        repo_ref: Optional[RepoRef] = None,
        repo_dir: Optional[PathLike] = None,
        repo_data: Optional[RepoData] = None,
    ):
        if repo_dir is not None:
            repo_data = LocalRepoData(repo_dir=str(repo_dir))
        elif repo_data is None:
            raise ValueError("No local repo data provided")

        if repo_ref is None:
            repo_ref = RepoRef(repo_id=slugify(Path(repo_data.repo_dir).name, repo_data.repo_dir))
        super().__init__(repo_ref, repo_data)

    def get_workflows(self, credentials=None) -> Dict[str, Dict[str, Any]]:
        return load_workflows(Path(self.repo_data.repo_dir) / ".dstack")


class TarIgnore:
    def __init__(
        self, root_dir: PathLike, ignore_files: List[str] = None, globs: List[str] = None
    ):
        self.root_dir = Path(root_dir)
        self.ignore_files = (
            ignore_files
            if ignore_files is not None
            else [".gitignore", ".git/info/exclude", ".dstackignore"]
        )
        self.ignore_globs: Dict[str, List[str]] = {"": globs or []}

    def load_ignore_file(self, path: str, ignore_file: Path):
        if path not in self.ignore_globs:
            self.ignore_globs[path] = []
        with ignore_file.open("r") as f:
            for line in f:
                line = self.rstrip(line.rstrip("\n")).rstrip("/")
                line = line.replace("\\ ", " ")
                if line.startswith("#") or not line:
                    continue
                self.ignore_globs[path].append(line)

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

    def ignore(self, path: str, sep="/") -> bool:
        if not path:
            return False
        tokens = (sep + path).split(sep)
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

    def __call__(self, tarinfo: tarfile.TarInfo) -> Optional[tarfile.TarInfo]:
        if self.ignore(tarinfo.path):
            return None
        abspath = self.root_dir / tarinfo.path
        if abspath.is_dir():
            for ignore_file in self.ignore_files:
                ignore_file = abspath / ignore_file
                if ignore_file.exists():
                    self.load_ignore_file(tarinfo.path, ignore_file)
        return tarinfo
