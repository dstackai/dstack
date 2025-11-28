from typing import List, Literal

from dstack._internal.core.models.common import CoreConfig, generate_dual_core_model
from dstack._internal.core.models.runs import Requirements
from dstack._internal.server.schemas.gpus import GpuGroup
from dstack._internal.utils.json_utils import pydantic_orjson_dumps_with_indent


class OfferCommandOutputConfig(CoreConfig):
    json_dumps = pydantic_orjson_dumps_with_indent


class OfferCommandOutput(generate_dual_core_model(OfferCommandOutputConfig)):
    """JSON output model for `dstack offer` command with GPU grouping."""

    project: str
    requirements: Requirements
    group_by: List[Literal["gpu", "backend", "region", "count"]]
    gpus: List[GpuGroup]
