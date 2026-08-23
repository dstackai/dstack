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


class GetPresetFileRequest(CoreModel):
    name_or_id: Annotated[str, Field(description="The preset id or name")]
    path: Annotated[
        str, Field(description="The preset-directory-relative path of the file to download")
    ]


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
    """What `get` returns: the record plus the stored spec. File contents are
    downloaded separately per archive mapping."""

    spec: PresetSpec
