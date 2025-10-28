import enum
import uuid
from datetime import datetime
from typing import List, Optional

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.runs import JobProvisioningData


class ComputeGroupStatus(str, enum.Enum):
    RUNNING = "running"
    TERMINATED = "terminated"


class ComputeGroupProvisioningData(CoreModel):
    compute_group_id: str
    compute_group_name: str
    backend: BackendType
    # In case backend provisions instance in another backend,
    # it may set that backend as base_backend.
    base_backend: Optional[BackendType] = None
    region: str
    job_provisioning_datas: List[JobProvisioningData]
    backend_data: Optional[str] = None  # backend-specific data in json


class ComputeGroup(CoreModel):
    """
    Compute group is a group of instances managed as a single unit via the provider API,
    i.e. instances are not created/deleted one-by-one but all at once.
    """

    id: uuid.UUID
    name: str
    project_name: str
    created_at: datetime
    status: ComputeGroupStatus
    provisioning_data: ComputeGroupProvisioningData
