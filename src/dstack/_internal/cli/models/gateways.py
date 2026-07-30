from typing import List

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.gateways import Gateway


class GatewayCommandOutput(CoreModel):
    """JSON output model for `dstack gateway` command."""

    project: str
    gateways: List[Gateway]
