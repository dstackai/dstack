import uuid
from typing import List, Optional

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.runs import JobProvisioningData


class ComputeGroupProvisioningData(CoreModel):
    compute_group_id: str
    compute_group_name: str
    job_provisioning_datas: List[JobProvisioningData]
    backend_data: Optional[str] = None  # backend-specific data in json


class ComputeGroup(CoreModel):
    id: uuid.UUID
    name: str
    provisioning_data: Optional[ComputeGroupProvisioningData] = None
