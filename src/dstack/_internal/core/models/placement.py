from enum import Enum

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel


class PlacementStrategy(str, Enum):
    CLUSTER = "cluster"


class PlacementGroupConfiguration(CoreModel):
    backend: BackendType
    region: str
    placement_strategy: PlacementStrategy


class PlacementGroup(CoreModel):
    name: str
    project_name: str
    configuration: PlacementGroupConfiguration
