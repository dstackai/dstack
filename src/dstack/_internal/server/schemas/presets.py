from datetime import datetime
from uuid import UUID

from pydantic import Field
from typing_extensions import Annotated

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.presets import PresetSpec


class PushPresetRequest(CoreModel):
    name: Annotated[str, Field(description="The registry preset name")]
    spec: Annotated[PresetSpec, Field(description="The preset to push")]


class GetPresetRequest(CoreModel):
    name_or_id: Annotated[
        str,
        Field(description=("The preset id, or a preset name resolving to its current version")),
    ]


class GetPresetFilesRequest(CoreModel):
    name_or_id: Annotated[str, Field(description="The preset id or name")]


class PushPresetResponse(CoreModel):
    """What `push` returns: the record the registry minted."""

    id: UUID
    name: str
    base: str
    repo: str
    created_at: datetime
    pushed_by: Annotated[str, Field(description="The username of the pusher")]
    is_current: Annotated[
        bool,
        Field(
            description=(
                "Whether the name currently resolves to this preset."
                " Derived when read: a later push under the same name takes it over"
            )
        ),
    ]


class GetPresetResponse(PushPresetResponse):
    """What `get` returns: the record plus the stored spec. File contents come
    from `get_files`, which streams them all in one response."""

    spec: PresetSpec


# `get_files` streams archives back to back, each framed by its path and length,
# so neither side ever holds more than one archive: a 4-byte path length, the
# UTF-8 path, an 8-byte content length, then the archive.
PRESET_FILES_PATH_LENGTH_BYTES = 4
PRESET_FILES_CONTENT_LENGTH_BYTES = 8
