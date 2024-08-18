from gpuhunt import AcceleratorVendor

from dstack._internal.core.models.instances import Gpu


class TestGpu:
    def test_no_vendor_nvidia(self):
        gpu = Gpu.parse_obj(
            {
                "name": "T4",
                "memory_mib": 16,
            }
        )
        assert gpu.vendor == AcceleratorVendor.NVIDIA
        assert gpu.name == "T4"

    def test_no_vendor_tpu(self):
        gpu = Gpu.parse_obj(
            {
                "name": "tpu-v3",
                "memory_mib": 0,
            }
        )
        assert gpu.vendor == AcceleratorVendor.GOOGLE
        assert gpu.name == "v3"

    def test_vendor_cast_to_enum(self):
        gpu = Gpu.parse_obj(
            {
                "vendor": "AMD",
                "name": "MI300X",
                "memory_mib": 192,
            }
        )
        assert gpu.vendor == AcceleratorVendor.AMD
        assert gpu.name == "MI300X"
