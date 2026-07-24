import gpuhunt
import pytest

from dstack._internal.core.backends.base.offers import (
    filter_offers_by_requirements,
    gpu_matches_gpu_spec,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    Disk,
    Gpu,
    InstanceOffer,
    InstanceType,
    Resources,
)
from dstack._internal.core.models.resources import GPUSpec, ResourcesSpec
from dstack._internal.core.models.runs import Requirements

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


class TestFilterOffersByRequirementsDiskSize:
    """
    An offer with `disk.size_mib == 0` has an unknown disk size and must not be
    filtered out by the disk size requirement. This exercises both the
    `offer_to_catalog_item` mapping (`size_mib=0` -> `disk_size=None`) and
    `gpuhunt.matches` (ignores disk bounds when `disk_size is None`).
    """

    def make_offer(self, disk_size_mib: int) -> InstanceOffer:
        # cpus/memory are chosen to satisfy the default requirements so that only the
        # disk size decides whether the offer is filtered out.
        return InstanceOffer(
            backend=BackendType.SLURM,
            instance=InstanceType(
                name="test-instance",
                resources=Resources(
                    cpus=8,
                    memory_mib=64 * 1024,
                    gpus=[],
                    spot=False,
                    disk=Disk(size_mib=disk_size_mib),
                ),
            ),
            region="test-region",
            price=1.0,
        )

    def test_unknown_disk_size_ignores_disk_requirement(self):
        # An offer with a real 0 GB disk would satisfy neither the min nor the max
        # bound, so a match here proves the disk requirement is ignored entirely.
        offer = self.make_offer(disk_size_mib=0)
        requirements = Requirements(resources=ResourcesSpec(disk="100GB..200GB"))

        assert list(filter_offers_by_requirements([offer], requirements)) == [offer]

    def test_known_disk_size_below_min_is_filtered_out(self):
        # A non-zero disk size is still checked, so the requirement stays effective.
        offer = self.make_offer(disk_size_mib=50 * 1024)
        requirements = Requirements(resources=ResourcesSpec(disk="100GB.."))

        assert list(filter_offers_by_requirements([offer], requirements)) == []

    def test_known_disk_size_within_range_matches(self):
        offer = self.make_offer(disk_size_mib=150 * 1024)
        requirements = Requirements(resources=ResourcesSpec(disk="100GB..200GB"))

        assert list(filter_offers_by_requirements([offer], requirements)) == [offer]
