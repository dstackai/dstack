from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.endpoint_presets import EndpointPreset


class EndpointPresetListOutput(CoreModel):
    presets: list[EndpointPreset]
