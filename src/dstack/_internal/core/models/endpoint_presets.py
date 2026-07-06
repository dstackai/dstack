from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.resources import ResourcesSpec


class EndpointPresetReplicaSpecGroup(CoreModel):
    """Ordered to match service replica groups; "0" is the implicit group."""

    name: str
    resources: ResourcesSpec
    """Per-replica scheduling requirements used when applying the preset."""
    tested_resources: list[ResourcesSpec]
    """Exact resources of the replicas that were running when the preset was verified."""


class EndpointPreset(CoreModel):
    name: str
    model: str
    replica_spec_groups: list[EndpointPresetReplicaSpecGroup]


class EndpointPresetDetails(EndpointPreset):
    service: ServiceConfiguration
