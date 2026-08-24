from datetime import datetime
from typing import List, Optional
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


class ListPresetsRequest(CoreModel):
    project_name: Annotated[
        Optional[str], Field(description="Only list presets pushed to this project")
    ] = None
    username: Annotated[
        Optional[str], Field(description="Only list presets pushed by this user")
    ] = None
    base: Annotated[Optional[str], Field(description="Only list presets for this base model")] = (
        None
    )
    prev_created_at: Annotated[
        Optional[datetime], Field(description="The `created_at` of the last preset of the page")
    ] = None
    prev_id: Annotated[
        Optional[UUID], Field(description="The `id` of the last preset of the page")
    ] = None
    limit: Annotated[int, Field(description="The page size", ge=0, le=100)] = 100
    ascending: bool = False


class DeletePresetRequest(CoreModel):
    id: Annotated[UUID, Field(description="The preset to delete")]


class PushPresetResponse(CoreModel):
    """What `push` returns: the record the registry minted."""

    id: UUID
    name: Annotated[
        Optional[str],
        Field(
            description=(
                "The name while it resolves to this preset."
                " A later push under the same name takes it over, and this is then unset"
            )
        ),
    ]
    project_name: str
    base: str
    repo: str
    created_at: datetime
    pushed_by: Annotated[str, Field(description="The username of the pusher")]


class ListPresetsResponse(CoreModel):
    """What `list` returns: a record per preset, superseded ones included,
    without the specs, which `get` reads one at a time."""

    presets: List[PushPresetResponse]


class GetPresetResponse(PushPresetResponse):
    """What `get` returns: the record plus the stored spec. File contents come
    from `get_files`, which streams them all in one response."""

    spec: PresetSpec


# `get_files` streams archives back to back, each framed by its path and length,
# so neither side ever holds more than one archive: a 4-byte path length, the
# UTF-8 path, an 8-byte content length, then the archive.
PRESET_FILES_PATH_LENGTH_BYTES = 4
PRESET_FILES_CONTENT_LENGTH_BYTES = 8
