from typing import TypeVar

from dstack._internal.core.models.fleets import FleetSpec
from dstack._internal.core.models.gateways import GatewaySpec
from dstack._internal.core.models.runs import RunSpec
from dstack._internal.core.models.volumes import VolumeSpec

ApplySpec = TypeVar("ApplySpec", RunSpec, FleetSpec, VolumeSpec, GatewaySpec)
