from datetime import datetime
from typing import Optional
from uuid import UUID

from dstack._internal.core.models.common import CoreModel


class DeletePoolRequest(CoreModel):
    name: str
    force: bool


class CreatePoolRequest(CoreModel):
    name: str


class ShowPoolRequest(CoreModel):
    name: Optional[str]


class RemoveInstanceRequest(CoreModel):
    pool_name: str
    instance_name: str
    force: bool = False


class SetDefaultPoolRequest(CoreModel):
    pool_name: str


class ListPoolsRequest(CoreModel):
    project_name: Optional[str]
    pool_name: Optional[str]
    only_active: bool = False
    prev_created_at: Optional[datetime]
    prev_id: Optional[UUID]
    limit: int = 1000
    ascending: bool = False
