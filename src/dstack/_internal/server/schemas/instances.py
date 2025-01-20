from datetime import datetime
from typing import Optional
from uuid import UUID

from dstack._internal.core.models.common import CoreModel


class ListInstancesRequest(CoreModel):
    project_names: Optional[list[str]] = None
    fleet_ids: Optional[list[UUID]] = None
    only_active: bool = False
    prev_created_at: Optional[datetime] = None
    prev_id: Optional[UUID] = None
    limit: int = 1000
    ascending: bool = False
