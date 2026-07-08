from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.resources import ResourcesSpec


class EndpointPresetValidationReplica(CoreModel):
    resources: list[ResourcesSpec]
    """Exact resources for each running replica in this service replica group."""


class EndpointPresetValidation(CoreModel):
    replicas: list[EndpointPresetValidationReplica]
    """Ordered to match `ServiceConfiguration.replica_groups`."""


class EndpointPresetRecipe(CoreModel):
    id: str
    service: ServiceConfiguration
    validations: list[EndpointPresetValidation]


class EndpointPreset(CoreModel):
    model: str
    recipes: list[EndpointPresetRecipe]
