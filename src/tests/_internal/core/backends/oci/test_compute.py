import pytest

from dstack._internal.core.backends.oci.compute import _supported_instances
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceOffer,
    InstanceType,
    Resources,
)


def make_offer(shape_name: str) -> InstanceOffer:
    return InstanceOffer(
        backend=BackendType.OCI,
        instance=InstanceType(
            name=shape_name,
            resources=Resources(cpus=8, memory_mib=64 * 1024, gpus=[], spot=False),
        ),
        region="us-chicago-1",
        price=1.0,
    )


class TestSupportedInstances:
    @pytest.mark.parametrize(
        "shape_name",
        [
            "VM.Standard2.1",
            "BM.Standard.E5.192",
            "VM.GPU3.1",
            "BM.GPU4.8",
            "VM.GPU.A10.1",
            "BM.GPU.A10.4",
            "BM.GPU.A100-v2.8",
            "BM.GPU.L40S.4",
            "BM.GPU.H100.8",
            "BM.GPU.H200.8",
            "BM.GPU.B200.8",
            "BM.GPU.B300.8",
            "BM.GPU.RTXPRO.8",
        ],
    )
    def test_supported(self, shape_name: str):
        assert _supported_instances(make_offer(shape_name))

    @pytest.mark.parametrize(
        "shape_name",
        [
            # Flex shapes need OCPU/memory configuration
            "VM.Standard.E4.Flex",
            "VM.Optimized3.Flex",
            # Ampere A1 Arm CPUs and Grace superchips: no arm64 image
            "VM.Standard.A1.Flex",
            "BM.Standard.A1.160",
            "BM.GPU.GB200.4",
            "BM.GPU.GB300.4",
            # AMD Instinct: no ROCm image
            "BM.GPU.MI300X.8",
            "BM.GPU.MI355X.8",
            # Deprecated families
            "BM.GPU2.2",
            "VM.GPU2.1",
        ],
    )
    def test_unsupported(self, shape_name: str):
        assert not _supported_instances(make_offer(shape_name))
