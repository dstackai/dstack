from typing import List

from dstack._internal.core.models.common import CoreConfig, generate_dual_core_model
from dstack._internal.core.models.gateways import Gateway
from dstack._internal.utils.json_utils import pydantic_orjson_dumps_with_indent


class GatewayCommandOutputConfig(CoreConfig):
    json_dumps = pydantic_orjson_dumps_with_indent


class GatewayCommandOutput(generate_dual_core_model(GatewayCommandOutputConfig)):
    """JSON output model for `dstack gateway` command."""

    project: str
    gateways: List[Gateway]
