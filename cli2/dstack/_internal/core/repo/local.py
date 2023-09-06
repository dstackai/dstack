import tarfile
from pathlib import Path
from typing import BinaryIO, Optional

from typing_extensions import Literal

from dstack._internal.core.repo.base import Repo, RepoData, RepoInfo, RepoRef
from dstack._internal.utils.common import PathLike
from dstack._internal.utils.escape import escape_head
from dstack._internal.utils.hash import get_sha256, slugify
from dstack._internal.utils.ignore import GitIgnore


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


class TarIgnore(GitIgnore):
    def __call__(self, tarinfo: tarfile.TarInfo) -> Optional[tarfile.TarInfo]:
        if self.ignore(tarinfo.path):
            return None
        return tarinfo
