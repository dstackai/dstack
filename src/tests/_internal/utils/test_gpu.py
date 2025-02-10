import pytest

from dstack._internal.utils.gpu import (
    convert_amd_gpu_name,
    convert_intel_accelerator_name,
    convert_nvidia_gpu_name,
)


class TestConvertGpuName:
    @pytest.mark.parametrize(
        ["test_input", "expected"],
        [
            ("NVIDIA GeForce RTX 4060 Ti", "RTX4060Ti"),
            ("NVIDIA GeForce RTX 4060", "RTX4060"),
            ("NVIDIA RTX 4000 Ada Generation", "RTX4000Ada"),
            ("NVIDIA L4", "L4"),
            ("NVIDIA GH200 120GB", "GH200"),
            ("NVIDIA A100-SXM4-80GB", "A100"),
            ("NVIDIA A10G", "A10G"),
            ("NVIDIA L40S", "L40S"),
            ("NVIDIA H100 NVL", "H100NVL"),
            ("NVIDIA H100 80GB HBM3", "H100"),
            ("Tesla T4", "T4"),
        ],
    )
    def test_convert_nvidia_gpu_name(self, test_input, expected):
        assert convert_nvidia_gpu_name(test_input) == expected

    @pytest.mark.parametrize(
        ["test_input", "expected"],
        [
            # The following are asic.market_name from amd-smi collected in the wild
            ("MI300X-O", "MI300X"),
            ("Instinct MI210", "MI210"),
            ("AMD INSTINCT MI250 (MCM) OAM AC MBA", "MI250"),
            # The following are made-up examples
            ("MI300A", "MI300A"),
            ("Instinct MI325X", "MI325X"),
            ("AMD Radeon PRO W7900", "AMD Radeon PRO W7900"),
        ],
    )
    def test_convert_amd_gpu_name(self, test_input, expected):
        assert convert_amd_gpu_name(test_input) == expected

    @pytest.mark.parametrize(
        ["test_input", "expected"],
        [
            # The following are name from hl-smi collected in the wild
            ("HL-225", "Gaudi2"),
            # The following are made-up examples
            ("HL-225B", "Gaudi2"),
            ("HL-325L", "Gaudi3"),
            ("HL-338", "Gaudi3"),
            ("HL-1000", "HL-1000"),
        ],
    )
    def test_convert_intel_accelerator_name(self, test_input, expected):
        assert convert_intel_accelerator_name(test_input) == expected
