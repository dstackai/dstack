from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import Field

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.volumes import VolumeConfiguration


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
    configuration: VolumeConfiguration


class DeleteVolumesRequest(CoreModel):
    names: List[str]
