import io
import tarfile
from importlib import resources as impresources
from types import ModuleType
from typing import BinaryIO, Dict, Literal, Union

from dstack._internal.core.models.repos.base import BaseRepoInfo, Repo
from dstack._internal.utils.hash import get_sha256
from dstack._internal.utils.path import resolve_relative_path


class VirtualRepoException(Exception):
    """Base exception for VirtualRepo related errors."""


class VirtualRepoInfo(BaseRepoInfo):
    """Information about a virtual repository."""

    repo_type: Literal["virtual"] = "virtual"


class VirtualRunRepoData(VirtualRepoInfo):
    """Data class for run repo information in a virtual repository."""

    pass


class VirtualRepo(Repo):
    """
    Represents an in-memory repository, transferred as a tar ball.
    """

    run_repo_data: VirtualRunRepoData

    def __init__(self, repo_id: str):
        """Initialize a virtual repository."""
        self.repo_id = repo_id
        self.repo_dir = None
        self.files: Dict[str, bytes] = {}
        self.run_repo_data = VirtualRunRepoData()

    def add_file_from_package(self, package: Union[ModuleType, str], path: str) -> None:
        """
        Add a file from a package to the virtual repository.

        Args:
            package: The package containing the file.
            path: The path to the file within the package.
        """
        try:
            req_file = impresources.files(package) / path
            with req_file.open("rb") as f:
                self.add_file(path, f.read())
        except FileNotFoundError:
            raise VirtualRepoException(f"File {path} not found in package {package}.")
        except Exception as e:
            raise VirtualRepoException(
                f"An error occurred while adding the file from package: {e}"
            )

    def add_file(self, path: str, content: bytes) -> None:
        """
        Add a file with the given content to the virtual repository.

        Args:
            path: The path to the file.
            content: The content of the file.
        """
        try:
            self.files[resolve_relative_path(path).as_posix()] = content
        except Exception as e:
            raise VirtualRepoException(f"An error occurred while adding the file: {e}")

    def write_code_file(self, fp: BinaryIO) -> str:
        """
        Write the code file to the given file pointer.

        Args:
            fp: The file pointer to write the code to.

        Returns:
            The SHA256 hash of the written file.
        """
        try:
            with tarfile.TarFile(mode="w", fileobj=fp) as t:
                for path, content in sorted(self.files.items()):
                    info = tarfile.TarInfo(path)
                    info.size = len(content)
                    t.addfile(info, fileobj=io.BytesIO(initial_bytes=content))
            return get_sha256(fp)
        except tarfile.TarError:
            raise VirtualRepoException("Error occurred while creating the tar file.")
        except Exception as e:
            raise VirtualRepoException(f"An error occurred while writing the code file: {e}")
