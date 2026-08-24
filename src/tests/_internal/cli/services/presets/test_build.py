import gpuhunt
import pytest

from dstack._internal.cli.services.presets.build import set_service_gpu_vendor_from_verification
from dstack._internal.core.models.configurations import (
    DEFAULT_REPLICA_GROUP_NAME,
    ServiceConfiguration,
)
from dstack._internal.core.models.presets import PresetVerificationReplicaGroup
from dstack._internal.core.models.resources import ResourcesSpec

pytestmark = pytest.mark.windows


def _gpu_resources(name: str, *, vendor: str | None = None) -> ResourcesSpec:
    gpu = {"name": name, "memory": "48GB", "count": 1}
    if vendor is not None:
        gpu["vendor"] = vendor
    return ResourcesSpec.model_validate({"gpu": gpu})


class TestSetServiceGpuVendorFromVerification:
    def test_stamps_vendor_on_homogeneous_service_resources(self):
        service = ServiceConfiguration.model_validate(
            {
                "image": "vllm/vllm-openai:v0.11.0",
                "commands": ["vllm serve model"],
                "port": 8000,
                "model": "m",
                "resources": {"gpu": "40GB..48GB:1"},
            }
        )
        verified_on = [
            PresetVerificationReplicaGroup(
                name=DEFAULT_REPLICA_GROUP_NAME,
                replicas=[_gpu_resources("A6000")],
            )
        ]

        set_service_gpu_vendor_from_verification(service, verified_on)

        assert service.resources is not None
        assert service.resources.gpu is not None
        assert service.resources.gpu.vendor == gpuhunt.AcceleratorVendor.NVIDIA

    def test_stamps_vendor_on_each_replica_group_resources(self):
        service = ServiceConfiguration.model_validate(
            {
                "image": "vllm/vllm-openai:v0.11.0",
                "port": 8000,
                "model": "m",
                "groups": [
                    {
                        "name": "prefill",
                        "replicas": 1,
                        "commands": ["prefill"],
                        "resources": {"gpu": "40GB..48GB:1"},
                    },
                    {
                        "name": "decode",
                        "replicas": 1,
                        "commands": ["decode"],
                        "resources": {"gpu": "40GB..48GB:1"},
                    },
                ],
            }
        )
        verified_on = [
            PresetVerificationReplicaGroup(name="prefill", replicas=[_gpu_resources("H100")]),
            PresetVerificationReplicaGroup(name="decode", replicas=[_gpu_resources("A100")]),
        ]

        set_service_gpu_vendor_from_verification(service, verified_on)

        assert service.groups is not None
        assert service.groups[0].resources.gpu is not None
        assert service.groups[1].resources.gpu is not None
        assert service.groups[0].resources.gpu.vendor == gpuhunt.AcceleratorVendor.NVIDIA
        assert service.groups[1].resources.gpu.vendor == gpuhunt.AcceleratorVendor.NVIDIA
        assert service.resources.gpu is None or service.resources.gpu.vendor is None

    def test_rejects_service_vendor_that_does_not_match_verification(self):
        service = ServiceConfiguration.model_validate(
            {
                "image": "vllm/vllm-openai:v0.11.0",
                "commands": ["vllm serve model"],
                "port": 8000,
                "model": "m",
                "resources": {"gpu": "nvidia:40GB..48GB:1"},
            }
        )
        verified_on = [
            PresetVerificationReplicaGroup(
                name=DEFAULT_REPLICA_GROUP_NAME,
                replicas=[_gpu_resources("MI300X", vendor="amd")],
            )
        ]

        with pytest.raises(ValueError, match="GPU vendor does not match verification"):
            set_service_gpu_vendor_from_verification(service, verified_on)
