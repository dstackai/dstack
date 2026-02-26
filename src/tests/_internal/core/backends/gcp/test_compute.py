from dstack._internal.core.backends.gcp.compute import _supported_instances_and_zones
from dstack._internal.core.backends.gcp.models import GCPConfig, GCPDefaultCreds
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    Gpu,
    InstanceOffer,
    InstanceType,
    Resources,
)


def _make_offer(instance_name: str, region: str = "us-central1-a", gpus=None) -> InstanceOffer:
    if gpus is None:
        gpus = []
    return InstanceOffer(
        backend=BackendType.GCP,
        instance=InstanceType(
            name=instance_name,
            resources=Resources(
                cpus=8,
                memory_mib=32768,
                gpus=gpus,
                spot=False,
            ),
        ),
        region=region,
        price=1.0,
    )


class TestSupportedInstancesAndZones:
    def test_filters_tpu_when_disabled(self):
        f = _supported_instances_and_zones(["us-central1"], tpu=False)
        offer = _make_offer(
            "v5litepod-8",
            region="us-central1-b",
            gpus=[Gpu(name="v5litepod", memory_mib=16384)],
        )
        assert f(offer) is False

    def test_allows_single_host_tpu_when_enabled(self):
        f = _supported_instances_and_zones(["us-central1"], tpu=True)
        offer = _make_offer(
            "v5litepod-8",
            region="us-central1-b",
            gpus=[Gpu(name="v5litepod", memory_mib=16384)],
        )
        assert f(offer) is True

    def test_filters_multi_host_tpu_when_enabled(self):
        f = _supported_instances_and_zones(["us-central1"], tpu=True)
        offer = _make_offer(
            "v5litepod-16",
            region="us-central1-b",
            gpus=[Gpu(name="v5litepod", memory_mib=16384)],
        )
        assert f(offer) is False

    def test_allows_gpu_instances_regardless_of_tpu_flag(self):
        f = _supported_instances_and_zones(["us-central1"], tpu=False)
        offer = _make_offer(
            "a2-highgpu-1g",
            region="us-central1-b",
            gpus=[Gpu(name="A100", memory_mib=40960)],
        )
        assert f(offer) is True


class TestGCPConfigAllowTpu:
    def _make_config(self, tpu=None) -> GCPConfig:
        return GCPConfig(
            project_id="test-project",
            creds=GCPDefaultCreds(),
            tpu=tpu,
        )

    def test_default(self):
        config = self._make_config(tpu=None)
        assert config.allow_tpu is False

    def test_explicit_true(self):
        config = self._make_config(tpu=True)
        assert config.allow_tpu is True
