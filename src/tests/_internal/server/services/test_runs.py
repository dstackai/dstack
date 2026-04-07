import pytest

from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.server.services.jobs import check_can_attach_job_volumes
from dstack._internal.server.testing.common import (
    get_volume,
)


class TestCanAttachRunVolumes:
    @pytest.mark.asyncio
    async def test_can_attach(self):
        vol11 = get_volume(name="vol11")
        vol11.configuration.backend = BackendType.AWS
        vol11.configuration.region = "eu-west-1"
        vol12 = get_volume(name="vol12")
        vol12.configuration.backend = BackendType.AWS
        vol12.configuration.region = "eu-west-2"
        vol21 = get_volume(name="vol21")
        vol21.configuration.backend = BackendType.AWS
        vol21.configuration.region = "eu-west-1"
        vol22 = get_volume(name="vol22")
        vol22.configuration.backend = BackendType.AWS
        vol22.configuration.region = "eu-west-2"
        volumes = [[vol11, vol12], [vol21, vol22]]
        check_can_attach_job_volumes(volumes)

    @pytest.mark.asyncio
    async def test_cannot_attach_different_mount_points_with_different_backends_regions(self):
        vol1 = get_volume(name="vol11")
        vol1.configuration.backend = BackendType.AWS
        vol1.configuration.region = "eu-west-1"
        vol2 = get_volume(name="vol12")
        vol2.configuration.backend = BackendType.AWS
        vol2.configuration.region = "eu-west-2"
        volumes = [[vol1], [vol2]]
        with pytest.raises(ServerClientError):
            check_can_attach_job_volumes(volumes)

    @pytest.mark.asyncio
    async def test_cannot_attach_same_volume_at_different_mount_points(self):
        vol1 = get_volume(name="vol11")
        vol1.configuration.backend = BackendType.AWS
        vol1.configuration.region = "eu-west-1"
        volumes = [[vol1], [vol1]]
        with pytest.raises(ServerClientError):
            check_can_attach_job_volumes(volumes)
