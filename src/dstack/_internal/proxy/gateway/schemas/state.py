from typing import Optional

from dstack._internal.core.models.common import CoreModel
from dstack._internal.proxy.gateway.schemas.services import ServiceListItem


class StateSummaryResponse(CoreModel):
    """The model is minimal to allow for frequent polling by the server"""

    services: list[ServiceListItem]
    config_hash: Optional[str] = None
    """The hash sent by the server along with the current config"""
