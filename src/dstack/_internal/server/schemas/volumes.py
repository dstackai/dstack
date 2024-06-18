from typing import List

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.volumes import VolumeConfiguration


class GetVolumeRequest(CoreModel):
    name: str


class CreateVolumeRequest(CoreModel):
    configuration: VolumeConfiguration


class DeleteVolumesRequest(CoreModel):
    names: List[str]
