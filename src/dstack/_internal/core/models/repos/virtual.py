import io
import tarfile
from importlib import resources as impresources
from types import ModuleType
from typing import BinaryIO, Dict, Literal, Union

from dstack._internal.core.models.repos.base import BaseRepoInfo, Repo
from dstack._internal.utils.hash import get_sha256
from dstack._internal.utils.path import resolve_relative_path

DEFAULT_VIRTUAL_REPO_ID = "none"


class VirtualRepoInfo(BaseRepoInfo):
    repo_type: Literal["virtual"] = "virtual"


class VirtualRunRepoData(VirtualRepoInfo):
    pass


class VirtualRepo(Repo):
    """
    Allows mounting a repo created programmatically.

    Example:

    ```python
    virtual_repo = VirtualRepo(repo_id="some-unique-repo-id")
    virtual_repo.add_file_from_package(package=some_package, path="requirements.txt")
    virtual_repo.add_file_from_package(package=some_package, path="train.py")

    run = client.runs.apply_configuration(
        configuration=...,
        repo=virtual_repo,
    )
    ```

    Attributes:
        repo_id: A unique identifier of the repo

    """

    run_repo_data: VirtualRunRepoData

    def __init__(self, repo_id: str = DEFAULT_VIRTUAL_REPO_ID):
        self.repo_id = repo_id
        self.repo_dir = None
        self.files: Dict[str, bytes] = {}
        self.run_repo_data = VirtualRunRepoData()

    def add_file_from_package(self, package: Union[ModuleType, str], path: str):
        """
        Includes a file from a given package to the repo.

        Attributes:
            package (Union[ModuleType, str]): A package to include the file from.
            path (str): The path to the file to include to the repo. Must be relative to the package directory.
        """

        req_file = impresources.files(package) / path
        with req_file.open("rb") as f:
            self.add_file(path, f.read())

    def add_file(self, path: str, content: bytes):
        """
        Adds a given file to the repo.

        Attributes:
            path (str): The path inside the repo to add the file.
            content (bytes): The contents of the file.
        """

        self.files[resolve_relative_path(path).as_posix()] = content

    def write_code_file(self, fp: BinaryIO) -> str:
        with tarfile.TarFile(mode="w", fileobj=fp) as t:
            for path, content in sorted(self.files.items()):
                info = tarfile.TarInfo(path)
                info.size = len(content)
                t.addfile(info, fileobj=io.BytesIO(initial_bytes=content))
        return get_sha256(fp)

    def get_repo_info(self) -> VirtualRepoInfo:
        return VirtualRepoInfo()
