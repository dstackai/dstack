import logging

import pytest
from gpuhunt import AcceleratorVendor

from dstack._internal.core.backends.kubernetes.resources import (
    get_amd_gpu_from_node_labels,
    get_nvidia_gpu_from_node_labels,
    validate_label_key,
    validate_label_value,
)
from dstack._internal.core.models.instances import Gpu


class TestGetNvidiaGPUFromNodeLabels:
    def test_returns_none_if_no_labels(self):
        assert get_nvidia_gpu_from_node_labels({}) is None

    def test_returns_correct_memory_for_different_A100(self):
        assert get_nvidia_gpu_from_node_labels(
            {"nvidia.com/gpu.product": "A100-SXM4-40GB"}
        ) == Gpu(vendor=AcceleratorVendor.NVIDIA, name="A100", memory_mib=40 * 1024)

        assert get_nvidia_gpu_from_node_labels(
            {"nvidia.com/gpu.product": "A100-SXM4-80GB"}
        ) == Gpu(vendor=AcceleratorVendor.NVIDIA, name="A100", memory_mib=80 * 1024)


class TestGetAMDGPUFromNodeLabels:
    def test_returns_no_gpus_if_no_labels(self):
        assert get_amd_gpu_from_node_labels({}) is None

    def test_returns_known_gpu(self):
        assert get_amd_gpu_from_node_labels({"beta.amd.com/gpu.device-id.74b5": "4"}) == Gpu(
            vendor=AcceleratorVendor.AMD, name="MI300X", memory_mib=192 * 1024
        )

    def test_returns_known_gpu_if_multiple_device_ids_match_the_same_gpu(self):
        # 4x AMD Instinct MI300X VF + 4x AMD Instinct MI300X
        labels = {"beta.amd.com/gpu.device-id.74b5": "4", "beta.amd.com/gpu.device-id.74a1": "4"}
        assert get_amd_gpu_from_node_labels(labels) == Gpu(
            vendor=AcceleratorVendor.AMD, name="MI300X", memory_mib=192 * 1024
        )

    def test_returns_none_if_device_id_is_unknown(self, caplog: pytest.LogCaptureFixture):
        caplog.set_level(logging.WARNING)
        assert get_amd_gpu_from_node_labels({"beta.amd.com/gpu.device-id.ffff": "4"}) is None
        assert "Unknown AMD GPU device id: FFFF" in caplog.text

    def test_returns_none_if_multiple_gpu_models(self, caplog: pytest.LogCaptureFixture):
        caplog.set_level(logging.WARNING)
        # 4x AMD Instinct MI300X VF + 4x AMD Instinct MI325X
        labels = {"beta.amd.com/gpu.device-id.74b5": "4", "beta.amd.com/gpu.device-id.74a5": "4"}
        assert get_amd_gpu_from_node_labels(labels) is None
        assert "Multiple AMD GPU models detected" in caplog.text


class TestLabelValidation:
    @pytest.mark.parametrize(
        "key",
        [
            pytest.param("env", id="private"),
            pytest.param("k8s.example.com/Valid.Label_Name-1", id="prefixed"),
        ],
    )
    def test_valid_key(self, key: str):
        validate_label_key(key)

    @pytest.mark.parametrize(
        ["key", "expected_error"],
        [
            pytest.param("app.kubernetes.io//name", "Too many segments", id="too-many-segments"),
            pytest.param("/name", "Empty prefix", id="empty-prefix"),
            pytest.param("a" * 254 + "/name", "Prefix too long", id="too-long-prefix"),
            pytest.param("invalid prefix/name", "Invalid prefix", id="space-in-prefix"),
            pytest.param("my_app/name", "Invalid prefix", id="underscore-in-prefix"),
            pytest.param("-invalid/name", "Invalid prefix", id="leading-dash-in-prefix"),
            pytest.param("invalid-/name", "Invalid prefix", id="trailing-dash-in-prefix"),
            pytest.param("Invalid/name", "Invalid prefix", id="uppercase-in-prefix"),
            pytest.param("", "Empty name", id="empty-name-no-prefix"),
            pytest.param("prefix/", "Empty name", id="empty-name-with-prefix"),
            pytest.param("a" * 64, "Name too long", id="too-long-name-no-prefix"),
            pytest.param("prefix/" + "a" * 64, "Name too long", id="too-long-name-with-prefix"),
            pytest.param("-name", "Invalid name", id="leading-dash-in-name"),
            pytest.param("name-", "Invalid name", id="trailing-dash-in-name"),
        ],
    )
    def test_invalid_key(self, key: str, expected_error: str):
        with pytest.raises(ValueError, match=expected_error):
            validate_label_key(key)

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("", id="empty"),
            pytest.param("Valid.Label_Value-1", id="non-empty"),
        ],
    )
    def test_valid_value(self, value: str):
        validate_label_value(value)

    @pytest.mark.parametrize(
        ["value", "expected_error"],
        [
            pytest.param("a" * 64, "Value too long", id="too-long"),
            pytest.param("invalid value", "Invalid value", id="space"),
            pytest.param("-invalid", "Invalid value", id="leading-dash"),
            pytest.param("invalid-", "Invalid value", id="trailing-dash"),
        ],
    )
    def test_invalid_value(self, value: str, expected_error: str):
        with pytest.raises(ValueError, match=expected_error):
            validate_label_value(value)
