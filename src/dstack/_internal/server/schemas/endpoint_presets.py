from typing import List

from dstack._internal.core.models.common import CoreModel


class GetEndpointPresetRequest(CoreModel):
    model: str


class DeleteEndpointPresetsRequest(CoreModel):
    models: List[str]
