import pytest

from dstack import version
from dstack._internal.core.backends.azure.compute import VMImageVariant
from dstack._internal.core.models.instances import Gpu, InstanceType, Resources


class TestVMImageVariant:
    @pytest.mark.parametrize(
        ["instance_type", "expected_variant"],
        [
            [
                InstanceType(
                    name="NV6ads_A10_v5",
                    resources=Resources(
                        cpus=6,
                        memory_mib=55000,
                        gpus=[Gpu(name="NVIDIA A10-4Q", memory_mib=4000)],
                        spot=True,
                    ),
                ),
                VMImageVariant.GRID,
            ],
            [
                InstanceType(
                    name="NV4as_v4",
                    resources=Resources(
                        cpus=4,
                        memory_mib=14000,
                        gpus=[Gpu(name="Tesla T4", memory_mib=16000)],
                        spot=True,
                    ),
                ),
                VMImageVariant.CUDA,
            ],
            [
                InstanceType(
                    name="DS1_v2",
                    resources=Resources(
                        cpus=1,
                        memory_mib=3500,
                        gpus=[],
                        spot=True,
                    ),
                ),
                VMImageVariant.STANDARD,
            ],
        ],
    )
    def test_from_instance_type(
        self, instance_type: InstanceType, expected_variant: VMImageVariant
    ):
        assert VMImageVariant.from_instance_type(instance_type) == expected_variant

    @pytest.mark.parametrize(
        ["variant", "expected_name"],
        [
            [VMImageVariant.GRID, f"dstack-grid-{version.base_image}"],
            [VMImageVariant.CUDA, f"dstack-cuda-{version.base_image}"],
            [VMImageVariant.STANDARD, f"dstack-{version.base_image}"],
        ],
    )
    def test_get_image_name(self, variant: VMImageVariant, expected_name: str):
        assert variant.get_image_name() == expected_name
