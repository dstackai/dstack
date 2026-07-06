from typing import List

from dstack._internal.core.models.common import CoreModel


class GetEndpointPresetRequest(CoreModel):
    name: str


class DeleteEndpointPresetsRequest(CoreModel):
    names: List[str]
