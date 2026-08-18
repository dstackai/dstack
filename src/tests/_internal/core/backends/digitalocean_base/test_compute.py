from unittest.mock import Mock, patch

import gpuhunt
import pytest

from dstack._internal.core.backends.digitalocean_base.compute import BaseDigitalOceanCompute
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    Gpu,
    InstanceOffer,
    InstanceType,
    Resources,
)

pytestmark = pytest.mark.windows


def _offer(gpus: list[Gpu]) -> InstanceOffer:
    return InstanceOffer(
        backend=BackendType.AMDDEVCLOUD,
        instance=InstanceType(
            name="test-instance",
            resources=Resources(cpus=8, memory_mib=65536, spot=False, gpus=gpus),
        ),
        region="atl1",
        price=1.99,
    )


@pytest.fixture
def compute() -> BaseDigitalOceanCompute:
    with patch("dstack._internal.core.backends.digitalocean_base.compute.DigitalOceanAPIClient"):
        return BaseDigitalOceanCompute(
            config=Mock(creds=Mock(api_key="key"), regions=None, project_name=None),
            api_url="https://api.devcloud.amd.com",
            type=BackendType.AMDDEVCLOUD,
        )


class TestGetImageForInstance:
    def test_amd_gpu_image_ships_no_docker(self, compute):
        gpu = Gpu(vendor=gpuhunt.AcceleratorVendor.AMD, name="MI300X", memory_mib=196608)

        image = compute._get_image_for_instance(_offer([gpu]))

        assert image.slug == "gpu-amd-base"
        assert image.ships_docker is False

    def test_nvidia_gpu_images_ship_docker(self, compute):
        gpu = Gpu(vendor=gpuhunt.AcceleratorVendor.NVIDIA, name="H100", memory_mib=81920)

        single = compute._get_image_for_instance(_offer([gpu]))
        eight = compute._get_image_for_instance(_offer([gpu] * 8))

        assert single.slug == "gpu-h100x1-base"
        assert eight.slug == "gpu-h100x8-base"
        assert single.ships_docker is True
        assert eight.ships_docker is True

    def test_cpu_image_ships_no_docker(self, compute):
        image = compute._get_image_for_instance(_offer([]))

        assert image.slug == "ubuntu-24-04-x64"
        assert image.ships_docker is False
