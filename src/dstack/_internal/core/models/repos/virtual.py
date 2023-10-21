import io
import tarfile
from importlib import resources as impresources
from types import ModuleType
from typing import BinaryIO, Dict, Literal, Union

from dstack._internal.core.models.repos.base import BaseRepoInfo, Repo
from dstack._internal.utils.hash import get_sha256
from dstack._internal.utils.path import resolve_relative_path


class VirtualRepoInfo(BaseRepoInfo):
    repo_type: Literal["virtual"] = "virtual"


class VirtualRunRepoData(VirtualRepoInfo):
    pass


class VirtualRepo(Repo):
    """Represents in-memory repo, transferred as a tar ball"""

    run_repo_data: VirtualRunRepoData

    def __init__(self, repo_id: str):
        self.repo_id = repo_id
        self.repo_dir = None
        self.files: Dict[str, bytes] = {}
        self.run_repo_data = VirtualRunRepoData()

    def add_file_from_package(self, package: Union[ModuleType, str], path: str):
        req_file = impresources.files(package) / path
        with req_file.open("rb") as f:
            self.add_file(path, f.read())

    def add_file(self, path: str, content: bytes):
        self.files[resolve_relative_path(path).as_posix()] = content

    def write_code_file(self, fp: BinaryIO) -> str:
        with tarfile.TarFile(mode="w", fileobj=fp) as t:
            for path, content in sorted(self.files.items()):
                info = tarfile.TarInfo(path)
                info.size = len(content)
                t.addfile(info, fileobj=io.BytesIO(initial_bytes=content))
        return get_sha256(fp)
