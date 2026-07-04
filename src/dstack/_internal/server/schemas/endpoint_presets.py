from typing import List

from dstack._internal.core.models.common import CoreModel


class DeleteEndpointPresetsRequest(CoreModel):
    names: List[str]
