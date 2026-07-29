from datetime import datetime
from typing import Annotated, List, Optional
from uuid import UUID

from pydantic import Field

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.volumes import AnyVolumeConfiguration


class ListVolumesRequest(CoreModel):
    project_name: Optional[str] = None
    only_active: bool = False
    prev_created_at: Optional[datetime] = None
    prev_id: Optional[UUID] = None
    limit: int = Field(100, ge=0, le=100)
    ascending: bool = False


class GetVolumeRequest(CoreModel):
    name: str


class CreateVolumeRequest(CoreModel):
    configuration: Annotated[AnyVolumeConfiguration, Field(discriminator="backend")]


class DeleteVolumesRequest(CoreModel):
    names: List[str]
