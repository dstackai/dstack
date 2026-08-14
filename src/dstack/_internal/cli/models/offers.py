from typing import List, Literal, Optional

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.gpus import GpuGroup
from dstack._internal.core.models.instances import InstanceOfferWithAvailability
from dstack._internal.core.models.resources import ResourcesSpec


class OfferRequirements(CoreModel):
    """Profile/requirements output model for CLI commands."""

    resources: ResourcesSpec
    max_price: Optional[float] = None
    spot: Optional[bool] = None
    reservation: Optional[str] = None


class OfferCommandOutput(CoreModel):
    """JSON output model for `dstack offer` command."""

    project: str
    user: str
    requirements: OfferRequirements
    offers: List[InstanceOfferWithAvailability]
    total_offers: int


class OfferCommandGroupByGpuOutput(CoreModel):
    """JSON output model for `dstack offer` command with GPU grouping."""

    project: str
    requirements: OfferRequirements
    group_by: List[Literal["gpu", "backend", "region", "count"]]
    gpus: List[GpuGroup]
