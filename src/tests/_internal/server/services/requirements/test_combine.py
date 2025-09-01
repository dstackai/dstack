from typing import Optional

import gpuhunt
import pytest

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.profiles import SpotPolicy
from dstack._internal.core.models.resources import (
    ComputeCapability,
    CPUSpec,
    DiskSpec,
    GPUSpec,
    Memory,
    Range,
    ResourcesSpec,
)
from dstack._internal.core.models.runs import Requirements
from dstack._internal.server.services.requirements.combine import (
    CombineError,
    Profile,
    _combine_cpu,
    _combine_gpu_optional,
    _combine_idle_duration_optional,
    _combine_resources,
    _combine_spot_policy_optional,
    _intersect_lists_optional,
    combine_fleet_and_run_profiles,
    combine_fleet_and_run_requirements,
)


class TestCombineFleetAndRunProfiles:
    def test_returns_the_same_profile_if_profiles_identical(self):
        profile = Profile(
            backends=[BackendType.AWS],
            regions=["us-west2"],
            availability_zones=None,
            instance_types=None,
            reservation="r-12345",
            spot_policy=SpotPolicy.AUTO,
            idle_duration=3600,
            tags={"tag": "value"},
        )
        assert combine_fleet_and_run_profiles(profile, profile) == profile

    @pytest.mark.parametrize(
        argnames=["fleet_profile", "run_profile", "expected_profile"],
        argvalues=[
            pytest.param(
                Profile(),
                Profile(),
                Profile(),
                id="empty_profile",
            ),
            pytest.param(
                Profile(
                    backends=[BackendType.AWS, BackendType.GCP],
                    regions=["eu-west1", "europe-west-4"],
                    instance_types=["instance1"],
                    reservation="r-1",
                    spot_policy=SpotPolicy.AUTO,
                    idle_duration=3600,
                    tags={"tag1": "value1"},
                ),
                Profile(
                    backends=[BackendType.GCP, BackendType.RUNPOD],
                    regions=["eu-west2", "europe-west-4"],
                    instance_types=["instance2"],
                    reservation="r-1",
                    spot_policy=SpotPolicy.SPOT,
                    idle_duration=7200,
                    tags={"tag2": "value2"},
                ),
                Profile(
                    backends=[BackendType.GCP],
                    regions=["europe-west-4"],
                    instance_types=[],
                    reservation="r-1",
                    spot_policy=SpotPolicy.SPOT,
                    idle_duration=3600,
                    tags={"tag1": "value1", "tag2": "value2"},
                ),
                id="compatible_profiles",
            ),
            pytest.param(
                Profile(
                    spot_policy=SpotPolicy.SPOT,
                ),
                Profile(
                    spot_policy=SpotPolicy.ONDEMAND,
                ),
                None,
                id="incompatible_profiles",
            ),
        ],
    )
    def test_combines_profiles(
        self,
        fleet_profile: Profile,
        run_profile: Profile,
        expected_profile: Optional[Profile],
    ):
        assert combine_fleet_and_run_profiles(fleet_profile, run_profile) == expected_profile


class TestCombineFleetAndRunRequirements:
    def test_returns_the_same_requirements_if_requirements_identical(self):
        requirements = Requirements(
            resources=ResourcesSpec(gpu=GPUSpec(count=Range(min=2, max=None))),
            max_price=100,
            spot=False,
            reservation="r-1",
        )
        assert combine_fleet_and_run_requirements(requirements, requirements) == requirements

    @pytest.mark.parametrize(
        argnames=["fleet_requirements", "run_requirements", "expected_requirements"],
        argvalues=[
            pytest.param(
                Requirements(
                    resources=ResourcesSpec(gpu=GPUSpec(count=Range(min=1, max=3))),
                    max_price=100,
                    spot=False,
                ),
                Requirements(
                    resources=ResourcesSpec(gpu=GPUSpec(count=Range(min=3, max=4))),
                    max_price=50,
                    spot=None,
                ),
                Requirements(
                    resources=ResourcesSpec(gpu=GPUSpec(count=Range(min=3, max=3))),
                    max_price=50,
                    spot=False,
                ),
                id="compatible_requirements",
            ),
            pytest.param(
                Requirements(
                    resources=ResourcesSpec(gpu=GPUSpec(count=Range(min=1, max=2))),
                ),
                Requirements(resources=ResourcesSpec(gpu=GPUSpec(count=Range(min=3, max=4)))),
                None,
                id="incompatible_requirements",
            ),
        ],
    )
    def test_combines_requirements(
        self,
        fleet_requirements: Requirements,
        run_requirements: Requirements,
        expected_requirements: Optional[Requirements],
    ):
        assert (
            combine_fleet_and_run_requirements(fleet_requirements, run_requirements)
            == expected_requirements
        )


class TestIntersectLists:
    def test_both_none_returns_none(self):
        assert _intersect_lists_optional(None, None) is None

    def test_first_none_returns_copy_of_second(self):
        list2 = ["a", "b", "c"]
        result = _intersect_lists_optional(None, list2)
        assert result == list2
        assert result is not list2  # Should be a copy

    def test_second_none_returns_copy_of_first(self):
        list1 = ["x", "y", "z"]
        result = _intersect_lists_optional(list1, None)
        assert result == list1
        assert result is not list1  # Should be a copy

    def test_intersection_of_overlapping_lists(self):
        list1 = ["a", "b", "c", "d"]
        list2 = ["b", "c", "e", "f"]
        result = _intersect_lists_optional(list1, list2)
        assert result == ["b", "c"]

    def test_intersection_of_non_overlapping_lists(self):
        list1 = ["a", "b"]
        list2 = ["c", "d"]
        result = _intersect_lists_optional(list1, list2)
        assert result == []

    def test_intersection_preserves_order_from_first_list(self):
        list1 = ["c", "a", "b"]
        list2 = ["a", "b", "c"]
        result = _intersect_lists_optional(list1, list2)
        assert result == ["c", "a", "b"]

    def test_intersection_with_duplicates(self):
        list1 = ["a", "b", "a", "c"]
        list2 = ["a", "c", "d"]
        result = _intersect_lists_optional(list1, list2)
        assert result == ["a", "a", "c"]


class TestCombineIdleDuration:
    def test_both_none_returns_none(self):
        assert _combine_idle_duration_optional(None, None) is None

    def test_first_none_returns_second(self):
        assert _combine_idle_duration_optional(None, 3600) == 3600

    def test_second_none_returns_first(self):
        assert _combine_idle_duration_optional(7200, None) == 7200

    def test_both_positive_returns_minimum(self):
        assert _combine_idle_duration_optional(3600, 7200) == 3600
        assert _combine_idle_duration_optional(7200, 3600) == 3600

    def test_both_negative_returns_minimum(self):
        assert _combine_idle_duration_optional(-1, -2) == -2
        assert _combine_idle_duration_optional(-2, -1) == -2

    def test_both_zero_returns_zero(self):
        assert _combine_idle_duration_optional(0, 0) == 0

    def test_positive_and_negative_raises_error(self):
        with pytest.raises(
            CombineError, match="idle_duration values 3600 and -1 cannot be combined"
        ):
            _combine_idle_duration_optional(3600, -1)

    def test_negative_and_positive_raises_error(self):
        with pytest.raises(
            CombineError, match="idle_duration values -1 and 3600 cannot be combined"
        ):
            _combine_idle_duration_optional(-1, 3600)

    def test_zero_and_positive_returns_zero(self):
        assert _combine_idle_duration_optional(0, 3600) == 0
        assert _combine_idle_duration_optional(3600, 0) == 0

    def test_zero_and_negative_raises_error(self):
        with pytest.raises(CombineError, match="idle_duration values 0 and -1 cannot be combined"):
            _combine_idle_duration_optional(0, -1)
        with pytest.raises(CombineError, match="idle_duration values -1 and 0 cannot be combined"):
            _combine_idle_duration_optional(-1, 0)


class TestCombineSpotPolicy:
    def test_both_none_returns_none(self):
        assert _combine_spot_policy_optional(None, None) is None

    def test_first_none_returns_second(self):
        assert _combine_spot_policy_optional(None, SpotPolicy.SPOT) == SpotPolicy.SPOT
        assert _combine_spot_policy_optional(None, SpotPolicy.ONDEMAND) == SpotPolicy.ONDEMAND
        assert _combine_spot_policy_optional(None, SpotPolicy.AUTO) == SpotPolicy.AUTO

    def test_second_none_returns_first(self):
        assert _combine_spot_policy_optional(SpotPolicy.SPOT, None) == SpotPolicy.SPOT
        assert _combine_spot_policy_optional(SpotPolicy.ONDEMAND, None) == SpotPolicy.ONDEMAND
        assert _combine_spot_policy_optional(SpotPolicy.AUTO, None) == SpotPolicy.AUTO

    def test_auto_with_other_returns_other(self):
        assert _combine_spot_policy_optional(SpotPolicy.AUTO, SpotPolicy.SPOT) == SpotPolicy.SPOT
        assert (
            _combine_spot_policy_optional(SpotPolicy.AUTO, SpotPolicy.ONDEMAND)
            == SpotPolicy.ONDEMAND
        )
        assert _combine_spot_policy_optional(SpotPolicy.SPOT, SpotPolicy.AUTO) == SpotPolicy.SPOT
        assert (
            _combine_spot_policy_optional(SpotPolicy.ONDEMAND, SpotPolicy.AUTO)
            == SpotPolicy.ONDEMAND
        )

    def test_auto_with_auto_returns_auto(self):
        assert _combine_spot_policy_optional(SpotPolicy.AUTO, SpotPolicy.AUTO) == SpotPolicy.AUTO

    def test_same_non_auto_values_return_same(self):
        assert _combine_spot_policy_optional(SpotPolicy.SPOT, SpotPolicy.SPOT) == SpotPolicy.SPOT
        assert (
            _combine_spot_policy_optional(SpotPolicy.ONDEMAND, SpotPolicy.ONDEMAND)
            == SpotPolicy.ONDEMAND
        )

    def test_different_non_auto_values_raise_error(self):
        with pytest.raises(CombineError):
            _combine_spot_policy_optional(SpotPolicy.SPOT, SpotPolicy.ONDEMAND)
        with pytest.raises(CombineError):
            _combine_spot_policy_optional(SpotPolicy.ONDEMAND, SpotPolicy.SPOT)


class TestCombineResources:
    def test_combines_all_resource_specs(self):
        resources1 = ResourcesSpec(
            cpu=CPUSpec(arch=gpuhunt.CPUArchitecture.X86, count=Range(min=2, max=8)),
            memory=Range(min=Memory(4), max=Memory(16)),
            shm_size=Memory(2),
            gpu=GPUSpec(vendor=gpuhunt.AcceleratorVendor.NVIDIA),
            disk=DiskSpec(size=Range(min=Memory(100), max=Memory(500))),
        )
        resources2 = ResourcesSpec(
            cpu=CPUSpec(arch=gpuhunt.CPUArchitecture.X86, count=Range(min=4, max=6)),
            memory=Range(min=Memory(8), max=Memory(12)),
            shm_size=Memory(1),
            gpu=GPUSpec(vendor=gpuhunt.AcceleratorVendor.NVIDIA),
            disk=DiskSpec(size=Range(min=Memory(100), max=Memory(400))),
        )
        result = _combine_resources(resources1, resources2)
        expected = ResourcesSpec(
            cpu=CPUSpec(arch=gpuhunt.CPUArchitecture.X86, count=Range(min=4, max=6)),
            memory=Range(min=Memory(8), max=Memory(12)),
            shm_size=Memory(1),
            gpu=GPUSpec(vendor=gpuhunt.AcceleratorVendor.NVIDIA),
            disk=DiskSpec(size=Range(min=Memory(100), max=Memory(400))),
        )
        assert result == expected


class TestCombineCpu:
    def test_combines_compatible_cpu_specs(self):
        cpu1 = CPUSpec(arch=gpuhunt.CPUArchitecture.X86, count=Range(min=2, max=8))
        cpu2 = CPUSpec(arch=gpuhunt.CPUArchitecture.X86, count=Range(min=4, max=6))
        result = _combine_cpu(cpu1, cpu2)
        expected = CPUSpec(arch=gpuhunt.CPUArchitecture.X86, count=Range(min=4, max=6))
        assert result == expected

    def test_incompatible_architectures_raises_error(self):
        cpu1 = CPUSpec(arch=gpuhunt.CPUArchitecture.X86, count=Range(min=2, max=4))
        cpu2 = CPUSpec(arch=gpuhunt.CPUArchitecture.ARM, count=Range(min=2, max=4))
        with pytest.raises(CombineError):
            _combine_cpu(cpu1, cpu2)

    def test_non_overlapping_count_ranges_raises_error(self):
        cpu1 = CPUSpec(arch=gpuhunt.CPUArchitecture.X86, count=Range(min=1, max=2))
        cpu2 = CPUSpec(arch=gpuhunt.CPUArchitecture.X86, count=Range(min=4, max=6))
        with pytest.raises(CombineError):
            _combine_cpu(cpu1, cpu2)

    def test_handles_none_architecture(self):
        cpu1 = CPUSpec(arch=None, count=Range(min=2, max=4))
        cpu2 = CPUSpec(arch=gpuhunt.CPUArchitecture.X86, count=Range(min=2, max=4))
        result = _combine_cpu(cpu1, cpu2)
        expected = CPUSpec(arch=gpuhunt.CPUArchitecture.X86, count=Range(min=2, max=4))
        assert result == expected

    def test_both_none_architecture(self):
        cpu1 = CPUSpec(arch=None, count=Range(min=2, max=4))
        cpu2 = CPUSpec(arch=None, count=Range(min=3, max=5))
        result = _combine_cpu(cpu1, cpu2)
        expected = CPUSpec(arch=None, count=Range(min=3, max=4))
        assert result == expected


class TestCombineGpu:
    def test_both_none_returns_none(self):
        assert _combine_gpu_optional(None, None) is None

    def test_first_none_returns_copy_of_second(self):
        gpu2 = GPUSpec(count=Range(min=1, max=2))
        result = _combine_gpu_optional(None, gpu2)
        assert result == gpu2
        assert result is not gpu2  # Should be a copy

    def test_second_none_returns_copy_of_first(self):
        gpu1 = GPUSpec(count=Range(min=2, max=4))
        result = _combine_gpu_optional(gpu1, None)
        assert result == gpu1
        assert result is not gpu1  # Should be a copy

    def test_combines_compatible_gpu_specs(self):
        gpu1 = GPUSpec(
            vendor=gpuhunt.AcceleratorVendor.NVIDIA,
            name=["A100", "V100"],
            count=Range(min=1, max=4),
            memory=Range(min=Memory(8), max=Memory(32)),
            compute_capability=ComputeCapability((7, 0)),
        )
        gpu2 = GPUSpec(
            vendor=gpuhunt.AcceleratorVendor.NVIDIA,
            name=["V100", "T4"],
            count=Range(min=2, max=3),
            memory=Range(min=Memory(16), max=Memory(24)),
            compute_capability=ComputeCapability((7, 8)),
        )
        assert _combine_gpu_optional(gpu1, gpu2) == GPUSpec(
            vendor=gpuhunt.AcceleratorVendor.NVIDIA,
            name=["V100"],
            count=Range(min=2, max=3),
            memory=Range(min=Memory(16), max=Memory(24)),
            compute_capability=ComputeCapability((7, 0)),
        )

    def test_incompatible_vendors_raises_error(self):
        gpu1 = GPUSpec(vendor=gpuhunt.AcceleratorVendor.NVIDIA, count=Range(min=1, max=2))
        gpu2 = GPUSpec(vendor=gpuhunt.AcceleratorVendor.AMD, count=Range(min=1, max=2))
        with pytest.raises(CombineError):
            _combine_gpu_optional(gpu1, gpu2)

    def test_non_overlapping_count_ranges_raises_error(self):
        gpu1 = GPUSpec(count=Range(min=1, max=2))
        gpu2 = GPUSpec(count=Range(min=4, max=6))
        with pytest.raises(CombineError):
            _combine_gpu_optional(gpu1, gpu2)

    def test_non_overlapping_memory_ranges_raises_error(self):
        gpu1 = GPUSpec(count=Range(min=1, max=2), memory=Range(min=Memory(8), max=Memory(16)))
        gpu2 = GPUSpec(count=Range(min=1, max=2), memory=Range(min=Memory(32), max=Memory(64)))
        with pytest.raises(CombineError):
            _combine_gpu_optional(gpu1, gpu2)
