from typing import List, Literal, Optional

from dstack._internal.core.models.common import CoreConfig, generate_dual_core_model
from dstack._internal.core.models.gpus import GpuGroup
from dstack._internal.core.models.instances import InstanceOfferWithAvailability
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.utils.json_utils import pydantic_orjson_dumps_with_indent


class OfferRequirementsConfig(CoreConfig):
    json_dumps = pydantic_orjson_dumps_with_indent


class OfferRequirements(generate_dual_core_model(OfferRequirementsConfig)):
    """Profile/requirements output model for CLI commands."""

    resources: ResourcesSpec
    max_price: Optional[float] = None
    spot: Optional[bool] = None
    reservation: Optional[str] = None


class OfferCommandOutputConfig(CoreConfig):
    json_dumps = pydantic_orjson_dumps_with_indent


class OfferCommandOutput(generate_dual_core_model(OfferCommandOutputConfig)):
    """JSON output model for `dstack offer` command."""

    project: str
    user: str
    requirements: OfferRequirements
    offers: List[InstanceOfferWithAvailability]
    total_offers: int


class OfferCommandGroupByGpuOutputConfig(CoreConfig):
    json_dumps = pydantic_orjson_dumps_with_indent


class OfferCommandGroupByGpuOutput(generate_dual_core_model(OfferCommandGroupByGpuOutputConfig)):
    """JSON output model for `dstack offer` command with GPU grouping."""

    project: str
    requirements: OfferRequirements
    group_by: List[Literal["gpu", "backend", "region", "count"]]
    gpus: List[GpuGroup]
