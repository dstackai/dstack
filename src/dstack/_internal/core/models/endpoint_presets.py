from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.resources import ResourcesSpec


class EndpointPresetReplicaSpecGroup(CoreModel):
    name: str
    replica_specs: list[ResourcesSpec]


class EndpointPreset(CoreModel):
    name: str
    model: str
    replica_spec_groups: list[EndpointPresetReplicaSpecGroup]
