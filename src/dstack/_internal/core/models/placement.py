from enum import Enum
from typing import Optional

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel


class PlacementStrategy(str, Enum):
    CLUSTER = "cluster"


class PlacementGroupConfiguration(CoreModel):
    backend: BackendType
    region: str
    placement_strategy: PlacementStrategy


class PlacementGroupProvisioningData(CoreModel):
    backend: BackendType  # can be different from configuration backend
    backend_data: Optional[str] = None


class PlacementGroup(CoreModel):
    name: str
    project_name: str
    configuration: PlacementGroupConfiguration
    provisioning_data: Optional[PlacementGroupProvisioningData] = None
