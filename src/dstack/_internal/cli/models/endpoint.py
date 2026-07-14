from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.endpoint_presets import EndpointPresetRecipe


class EndpointPresetListOutput(CoreModel):
    recipes: list[EndpointPresetRecipe]
