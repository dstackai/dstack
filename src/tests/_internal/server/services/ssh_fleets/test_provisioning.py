import pytest

from dstack._internal.core.backends.base.compute import GoArchType
from dstack._internal.server.services.ssh_fleets.provisioning import host_info_to_instance_type


class TestHostInfoToInstanceType:
    @pytest.mark.parametrize("legacy_memory", [False, True])
    @pytest.mark.parametrize(
        "product,reported_mib,expected_mib,warns",
        [
            ("NVIDIA A100-SXM4-40GB", 39936, 40 * 1024, False),
            ("NVIDIA A100-SXM4-80GB", 80896, 80 * 1024, False),
            ("NVIDIA GeForce RTX 4090", 49140, 49140, True),
            ("NVIDIA Future GPU", 12345, 12345, True),
        ],
    )
    def test_normalizes_known_capacity_and_preserves_unresolved_measurements(
        self, product, reported_mib, expected_mib, warns, legacy_memory, caplog
    ):
        host_info = {
            "gpu_count": 2,
            "gpu_name": product,
            "gpu_memory": f"{reported_mib} MiB" if legacy_memory else reported_mib,
            "cpus": 16,
            "memory": 64 * 1024**3,
            "disk_size": 256 * 1024**3,
        }
        instance = host_info_to_instance_type(
            host_info, GoArchType.AMD64, context="provider=ssh, instance=test-host"
        )
        assert len(instance.resources.gpus) == 2
        assert all(gpu.memory_mib == expected_mib for gpu in instance.resources.gpus)
        assert bool(caplog.records) == warns
        if warns:
            assert "keeping reported VRAM" in caplog.text
            assert "provider=ssh, instance=test-host" in caplog.text
