from datetime import datetime
from typing import Annotated, List, Optional
from uuid import UUID

from pydantic import Field

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.volumes import AnyVolumeConfiguration


class ListVolumesRequest(CoreModel):
    project_name: Optional[str]
    only_active: bool = False
    prev_created_at: Optional[datetime]
    prev_id: Optional[UUID]
    limit: int = Field(100, ge=0, le=100)
    ascending: bool = False


class GetVolumeRequest(CoreModel):
    name: str


class CreateVolumeRequest(CoreModel):
    configuration: Annotated[AnyVolumeConfiguration, Field(discriminator="backend")]


class DeleteVolumesRequest(CoreModel):
    names: List[str]
