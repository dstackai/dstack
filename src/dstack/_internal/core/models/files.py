import pathlib
import string
from uuid import UUID

from pydantic import Field, validator
from typing_extensions import Annotated, Self

from dstack._internal.core.models.common import CoreModel


class FileArchive(CoreModel):
    id: UUID
    hash: str


class FilePathMapping(CoreModel):
    local_path: Annotated[
        str,
        Field(
            description=(
                "The path on the user's machine. Relative paths are resolved relative to"
                " the parent directory of the the configuration file"
            )
        ),
    ]
    path: Annotated[
        str,
        Field(
            description=(
                "The path in the container. Relative paths are resolved relative to"
                " the repo directory"
            )
        ),
    ]

    @classmethod
    def parse(cls, v: str) -> Self:
        local_path: str
        path: str
        parts = v.split(":")
        # A special case for Windows paths, e.g., `C:\path\to`, 'c:/path/to'
        if (
            len(parts) > 1
            and len(parts[0]) == 1
            and parts[0] in string.ascii_letters
            and parts[1][:1] in ["\\", "/"]
        ):
            parts = [f"{parts[0]}:{parts[1]}", *parts[2:]]
        if len(parts) == 1:
            local_path = path = parts[0]
        elif len(parts) == 2:
            local_path, path = parts
        else:
            raise ValueError(f"invalid file path mapping: {v}")
        return cls(local_path=local_path, path=path)

    @validator("path")
    def validate_path(cls, v) -> str:
        # True for `C:/.*`, False otherwise, including `/abs/unix/path`, `rel\windows\path`, etc.
        if pathlib.PureWindowsPath(v).is_absolute():
            raise ValueError(f"path must be a Unix file path: {v}")
        return v


class FileArchiveMapping(CoreModel):
    id: Annotated[UUID, Field(description="The File archive ID")]
    path: Annotated[str, Field(description="The path in the container")]
