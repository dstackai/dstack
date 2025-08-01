import tarfile
from pathlib import Path
from typing import BinaryIO, Optional

import ignore
import ignore.overrides
from typing_extensions import Literal

from dstack._internal.core.models.repos.base import BaseRepoInfo, Repo
from dstack._internal.utils.common import sizeof_fmt
from dstack._internal.utils.hash import get_sha256, slugify
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.path import PathLike

logger = get_logger(__name__)


class LocalRepoInfo(BaseRepoInfo):
    repo_type: Literal["local"] = "local"
    repo_dir: str


class LocalRunRepoData(LocalRepoInfo):
    pass


class LocalRepo(Repo):
    """
    Creates an instance of a local repo from a local path.

    Example:

    ```python
    run = client.runs.apply_configuration(
        configuration=...,
        repo=LocalRepo.from_dir("."), # Mount the current folder to the run
    )
    ```
    """

    run_repo_data: LocalRunRepoData

    @staticmethod
    def from_dir(repo_dir: PathLike) -> "LocalRepo":
        """
        Creates an instance of a local repo from a local path.

        Args:
            repo_dir: The path to a local folder.

        Returns:
            A local repo instance.
        """
        return LocalRepo(repo_dir=repo_dir)

    def __init__(
        self,
        *,
        repo_id: Optional[str] = None,
        repo_dir: Optional[PathLike] = None,
        repo_data: Optional[LocalRunRepoData] = None,
    ):
        self.repo_dir = repo_dir

        if repo_dir is not None:
            repo_data = LocalRunRepoData(repo_dir=str(repo_dir))
        elif repo_data is None:
            raise ValueError("No local repo data provided")

        if repo_id is None:
            repo_id = slugify(Path(repo_data.repo_dir).name, repo_data.repo_dir)

        self.repo_id = repo_id
        self.run_repo_data = repo_data

    def write_code_file(self, fp: BinaryIO) -> str:
        repo_path = Path(self.run_repo_data.repo_dir)
        with tarfile.TarFile(mode="w", fileobj=fp) as t:
            for entry in (
                ignore.WalkBuilder(repo_path)
                .overrides(ignore.overrides.OverrideBuilder(repo_path).add("!/.git/").build())
                .hidden(False)  # do not ignore files that start with a dot
                .require_git(False)  # respect git ignore rules even if not a git repo
                .add_custom_ignore_filename(".dstackignore")
                .build()
            ):
                entry_path_within_repo = entry.path().relative_to(repo_path)
                if entry_path_within_repo != Path("."):
                    t.add(entry.path(), arcname=entry_path_within_repo, recursive=False)
        logger.debug("Code file size: %s", sizeof_fmt(fp.tell()))
        return get_sha256(fp)

    def get_repo_info(self) -> LocalRepoInfo:
        return LocalRepoInfo(
            repo_dir=self.run_repo_data.repo_dir,
        )
