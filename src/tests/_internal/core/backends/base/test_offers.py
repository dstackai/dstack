import gpuhunt
import pytest

from dstack._internal.core.backends.base.offers import gpu_matches_gpu_spec
from dstack._internal.core.models.instances import Gpu
from dstack._internal.core.models.resources import GPUSpec

NVIDIA = gpuhunt.AcceleratorVendor.NVIDIA
AMD = gpuhunt.AcceleratorVendor.AMD


def make_gpu(name: str = "A100", memory_gib: int = 80, vendor=NVIDIA) -> Gpu:
    return Gpu(name=name, memory_mib=memory_gib * 1024, vendor=vendor)


class TestGpuMatchesGpuSpec:
    def test_empty_spec_matches_any_gpu(self):
        assert gpu_matches_gpu_spec(make_gpu(vendor=AMD), GPUSpec())

    def test_vendor_matches(self):
        assert gpu_matches_gpu_spec(make_gpu(vendor=NVIDIA), GPUSpec(vendor="nvidia"))

    def test_vendor_mismatch(self):
        assert not gpu_matches_gpu_spec(make_gpu(vendor=AMD), GPUSpec(vendor="nvidia"))

    def test_name_matches(self):
        assert gpu_matches_gpu_spec(make_gpu(name="A100"), GPUSpec(name="A100"))

    @pytest.mark.parametrize(
        ("gpu_name", "spec_name"),
        [("A100", "a100"), ("a100", "A100"), ("H100", "h100")],
    )
    def test_name_match_is_case_insensitive(self, gpu_name: str, spec_name: str):
        assert gpu_matches_gpu_spec(make_gpu(name=gpu_name), GPUSpec(name=spec_name))

    def test_name_matches_any_in_list(self):
        assert gpu_matches_gpu_spec(make_gpu(name="A100"), GPUSpec(name=["V100", "A100"]))

    def test_name_mismatch(self):
        assert not gpu_matches_gpu_spec(make_gpu(name="A100"), GPUSpec(name="V100"))

    def test_name_not_in_list(self):
        assert not gpu_matches_gpu_spec(make_gpu(name="A100"), GPUSpec(name=["V100", "H100"]))

    def test_memory_within_range(self):
        assert gpu_matches_gpu_spec(make_gpu(memory_gib=40), GPUSpec(memory="16GB..80GB"))

    def test_memory_equal_to_min(self):
        assert gpu_matches_gpu_spec(make_gpu(memory_gib=16), GPUSpec(memory="16GB.."))

    def test_memory_equal_to_max(self):
        assert gpu_matches_gpu_spec(make_gpu(memory_gib=80), GPUSpec(memory="..80GB"))

    def test_memory_below_min(self):
        assert not gpu_matches_gpu_spec(make_gpu(memory_gib=15), GPUSpec(memory="16GB.."))

    def test_memory_above_max(self):
        assert not gpu_matches_gpu_spec(make_gpu(memory_gib=100), GPUSpec(memory="..80GB"))

    def test_compute_capability_equal(self):
        # A100 has compute capability 8.0
        assert gpu_matches_gpu_spec(make_gpu(name="A100"), GPUSpec(compute_capability="8.0"))

    def test_compute_capability_gpu_higher_than_required(self):
        # A100 (8.0) satisfies the 7.0 minimum
        assert gpu_matches_gpu_spec(make_gpu(name="A100"), GPUSpec(compute_capability="7.0"))

    def test_compute_capability_gpu_lower_than_required(self):
        # A100 (8.0) does not satisfy the 9.0 minimum
        assert not gpu_matches_gpu_spec(make_gpu(name="A100"), GPUSpec(compute_capability="9.0"))

    def test_compute_capability_non_nvidia_never_matches(self):
        assert not gpu_matches_gpu_spec(
            make_gpu(name="MI300X", vendor=AMD), GPUSpec(compute_capability="8.0")
        )

    def test_compute_capability_unknown_gpu_name_never_matches(self):
        assert not gpu_matches_gpu_spec(
            make_gpu(name="UnknownGPU"), GPUSpec(compute_capability="8.0")
        )

    def test_all_constraints_match(self):
        spec = GPUSpec(
            vendor="nvidia",
            name="A100",
            memory="40GB..80GB",
            compute_capability="8.0",
        )
        assert gpu_matches_gpu_spec(make_gpu(name="A100", memory_gib=80), spec)

    def test_single_failing_constraint_rejects_gpu(self):
        # Everything matches except memory, which is below the minimum.
        spec = GPUSpec(vendor="nvidia", name="A100", memory="40GB..80GB")
        assert not gpu_matches_gpu_spec(make_gpu(name="A100", memory_gib=24), spec)
