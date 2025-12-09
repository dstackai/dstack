import logging

import pytest
from gpuhunt import AcceleratorVendor

from dstack._internal.core.backends.kubernetes.compute import (
    _get_amd_gpu_from_node_labels,
    _get_nvidia_gpu_from_node_labels,
)
from dstack._internal.core.models.instances import Gpu


class TestGetNvidiaGPUFromNodeLabels:
    def test_returns_none_if_no_labels(self):
        assert _get_nvidia_gpu_from_node_labels({}) is None

    def test_returns_correct_memory_for_different_A100(self):
        assert _get_nvidia_gpu_from_node_labels(
            {"nvidia.com/gpu.product": "A100-SXM4-40GB"}
        ) == Gpu(vendor=AcceleratorVendor.NVIDIA, name="A100", memory_mib=40 * 1024)

        assert _get_nvidia_gpu_from_node_labels(
            {"nvidia.com/gpu.product": "A100-SXM4-80GB"}
        ) == Gpu(vendor=AcceleratorVendor.NVIDIA, name="A100", memory_mib=80 * 1024)


class TestGetAMDGPUFromNodeLabels:
    def test_returns_no_gpus_if_no_labels(self):
        assert _get_amd_gpu_from_node_labels({}) is None

    def test_returns_known_gpu(self):
        assert _get_amd_gpu_from_node_labels({"beta.amd.com/gpu.device-id.74b5": "4"}) == Gpu(
            vendor=AcceleratorVendor.AMD, name="MI300X", memory_mib=192 * 1024
        )

    def test_returns_known_gpu_if_multiple_device_ids_match_the_same_gpu(self):
        # 4x AMD Instinct MI300X VF + 4x AMD Instinct MI300X
        labels = {"beta.amd.com/gpu.device-id.74b5": "4", "beta.amd.com/gpu.device-id.74a1": "4"}
        assert _get_amd_gpu_from_node_labels(labels) == Gpu(
            vendor=AcceleratorVendor.AMD, name="MI300X", memory_mib=192 * 1024
        )

    def test_returns_none_if_device_id_is_unknown(self, caplog: pytest.LogCaptureFixture):
        caplog.set_level(logging.WARNING)
        assert _get_amd_gpu_from_node_labels({"beta.amd.com/gpu.device-id.ffff": "4"}) is None
        assert "Unknown AMD GPU device id: FFFF" in caplog.text

    def test_returns_none_if_multiple_gpu_models(self, caplog: pytest.LogCaptureFixture):
        caplog.set_level(logging.WARNING)
        # 4x AMD Instinct MI300X VF + 4x AMD Instinct MI325X
        labels = {"beta.amd.com/gpu.device-id.74b5": "4", "beta.amd.com/gpu.device-id.74a5": "4"}
        assert _get_amd_gpu_from_node_labels(labels) is None
        assert "Multiple AMD GPU models detected" in caplog.text
