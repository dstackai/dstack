from typing import Optional

from dstack._internal.core.models.common import CoreModel


class ServerInfo(CoreModel):
    server_version: Optional[str]
