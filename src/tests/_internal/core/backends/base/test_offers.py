from typing import Optional

import gpuhunt
import pytest

from dstack._internal.core.backends.base.offers import (
    OfferDiskFitter,
    OfferMatcher,
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
from dstack._internal.core.models.resources import GPUSpec, Memory, Range, ResourcesSpec
from dstack._internal.core.models.runs import Requirements
from dstack._internal.server.testing.common import get_instance_offer_with_availability

NVIDIA = gpuhunt.AcceleratorVendor.NVIDIA
AMD = gpuhunt.AcceleratorVendor.AMD
GOOGLE = gpuhunt.AcceleratorVendor.GOOGLE
X86 = gpuhunt.CPUArchitecture.X86
ARM = gpuhunt.CPUArchitecture.ARM


def make_gpu(name: str = "A100", memory_gib: int = 80, vendor=NVIDIA) -> Gpu:
    return Gpu(name=name, memory_mib=memory_gib * 1024, vendor=vendor)


class TestGpuMatchesGpuSpec:
    def test_empty_spec_matches_any_gpu(self):
        assert gpu_matches_gpu_spec(make_gpu(vendor=AMD), GPUSpec())

    def test_vendor_matches(self):
        assert gpu_matches_gpu_spec(
            make_gpu(vendor=NVIDIA), GPUSpec.model_validate({"vendor": "nvidia"})
        )

    def test_vendor_mismatch(self):
        assert not gpu_matches_gpu_spec(
            make_gpu(vendor=AMD), GPUSpec.model_validate({"vendor": "nvidia"})
        )

    def test_name_matches(self):
        assert gpu_matches_gpu_spec(
            make_gpu(name="A100"), GPUSpec.model_validate({"name": "A100"})
        )

    @pytest.mark.parametrize(
        ("gpu_name", "spec_name"),
        [("A100", "a100"), ("a100", "A100"), ("H100", "h100")],
    )
    def test_name_match_is_case_insensitive(self, gpu_name: str, spec_name: str):
        assert gpu_matches_gpu_spec(
            make_gpu(name=gpu_name), GPUSpec.model_validate({"name": spec_name})
        )

    def test_name_matches_any_in_list(self):
        assert gpu_matches_gpu_spec(make_gpu(name="A100"), GPUSpec(name=["V100", "A100"]))

    def test_name_mismatch(self):
        assert not gpu_matches_gpu_spec(
            make_gpu(name="A100"), GPUSpec.model_validate({"name": "V100"})
        )

    def test_name_not_in_list(self):
        assert not gpu_matches_gpu_spec(make_gpu(name="A100"), GPUSpec(name=["V100", "H100"]))

    def test_memory_within_range(self):
        assert gpu_matches_gpu_spec(
            make_gpu(memory_gib=40), GPUSpec.model_validate({"memory": "16GB..80GB"})
        )

    def test_memory_equal_to_min(self):
        assert gpu_matches_gpu_spec(
            make_gpu(memory_gib=16), GPUSpec.model_validate({"memory": "16GB.."})
        )

    def test_memory_equal_to_max(self):
        assert gpu_matches_gpu_spec(
            make_gpu(memory_gib=80), GPUSpec.model_validate({"memory": "..80GB"})
        )

    def test_memory_below_min(self):
        assert not gpu_matches_gpu_spec(
            make_gpu(memory_gib=15), GPUSpec.model_validate({"memory": "16GB.."})
        )

    def test_memory_above_max(self):
        assert not gpu_matches_gpu_spec(
            make_gpu(memory_gib=100), GPUSpec.model_validate({"memory": "..80GB"})
        )

    def test_compute_capability_equal(self):
        # A100 has compute capability 8.0
        assert gpu_matches_gpu_spec(
            make_gpu(name="A100"), GPUSpec.model_validate({"compute_capability": "8.0"})
        )

    def test_compute_capability_gpu_higher_than_required(self):
        # A100 (8.0) satisfies the 7.0 minimum
        assert gpu_matches_gpu_spec(
            make_gpu(name="A100"), GPUSpec.model_validate({"compute_capability": "7.0"})
        )

    def test_compute_capability_gpu_lower_than_required(self):
        # A100 (8.0) does not satisfy the 9.0 minimum
        assert not gpu_matches_gpu_spec(
            make_gpu(name="A100"), GPUSpec.model_validate({"compute_capability": "9.0"})
        )

    def test_compute_capability_lookup_is_case_insensitive(self):
        assert gpu_matches_gpu_spec(
            make_gpu(name="a100"), GPUSpec.model_validate({"compute_capability": "8.0"})
        )

    def test_compute_capability_non_nvidia_never_matches(self):
        assert not gpu_matches_gpu_spec(
            make_gpu(name="MI300X", vendor=AMD),
            GPUSpec.model_validate({"compute_capability": "8.0"}),
        )

    def test_compute_capability_unknown_gpu_name_never_matches(self):
        assert not gpu_matches_gpu_spec(
            make_gpu(name="UnknownGPU"), GPUSpec.model_validate({"compute_capability": "8.0"})
        )

    def test_all_constraints_match(self):
        spec = GPUSpec.model_validate(
            {
                "vendor": "nvidia",
                "name": "A100",
                "memory": "40GB..80GB",
                "compute_capability": "8.0",
            }
        )
        assert gpu_matches_gpu_spec(make_gpu(name="A100", memory_gib=80), spec)

    def test_single_failing_constraint_rejects_gpu(self):
        # Everything matches except memory, which is below the minimum.
        spec = GPUSpec.model_validate({"vendor": "nvidia", "name": "A100", "memory": "40GB..80GB"})
        assert not gpu_matches_gpu_spec(make_gpu(name="A100", memory_gib=24), spec)


def make_offer(
    *,
    price: float = 1.0,
    spot: bool = False,
    cpu_arch: Optional[gpuhunt.CPUArchitecture] = None,
    cpus: int = 8,
    memory_mib: int = 64 * 1024,
    gpu_count: int = 0,
    gpu_name: str = "A100",
    gpu_memory_gib: int = 80,
    gpu_vendor: gpuhunt.AcceleratorVendor = NVIDIA,
    disk_gib: int = 100,
) -> InstanceOffer:
    """
    Returns an offer that matches the default requirements unless overridden.
    """
    gpus = [make_gpu(name=gpu_name, memory_gib=gpu_memory_gib, vendor=gpu_vendor)] * gpu_count
    return InstanceOffer(
        backend=BackendType.AWS,
        instance=InstanceType(
            name="test-instance",
            resources=Resources(
                cpus=cpus,
                memory_mib=memory_mib,
                gpus=gpus,
                spot=spot,
                disk=Disk(size_mib=disk_gib * 1024),
                cpu_arch=cpu_arch,
            ),
        ),
        region="test-region",
        price=price,
    )


def make_requirements(
    resources: Optional[dict] = None,
    *,
    spot: Optional[bool] = None,
    max_price: Optional[float] = None,
) -> Requirements:
    return Requirements(
        resources=ResourcesSpec.model_validate(resources or {}),
        spot=spot,
        max_price=max_price,
    )


def matches(offer: InstanceOffer, requirements: Requirements, check_disk: bool = True) -> bool:
    return OfferMatcher(requirements, check_disk=check_disk).matches(offer)


CPU_ONLY = make_offer()
A100 = make_offer(gpu_count=1)


class TestOfferMatcher:
    def test_default_requirements_match_cpu_and_gpu_offers(self):
        requirements = make_requirements()

        assert matches(CPU_ONLY, requirements)
        assert matches(A100, requirements)

    @pytest.mark.parametrize(
        ["price", "max_price", "expected"],
        [
            pytest.param(1.0, None, True, id="no-max-price"),
            pytest.param(1.0, 2.0, True, id="below-max"),
            pytest.param(1.0, 1.0, True, id="equal-to-max"),
            pytest.param(2.0, 1.0, False, id="above-max"),
        ],
    )
    def test_max_price(self, price: float, max_price: Optional[float], expected: bool):
        offer = make_offer(price=price)

        assert matches(offer, make_requirements(max_price=max_price)) is expected

    @pytest.mark.parametrize(
        ["offer_spot", "required_spot", "expected"],
        [
            pytest.param(False, None, True, id="any-on-demand"),
            pytest.param(True, None, True, id="any-spot"),
            pytest.param(True, True, True, id="spot-spot"),
            pytest.param(False, False, True, id="on-demand-on-demand"),
            pytest.param(False, True, False, id="spot-required-on-demand-offer"),
            pytest.param(True, False, False, id="on-demand-required-spot-offer"),
        ],
    )
    def test_spot(self, offer_spot: bool, required_spot: Optional[bool], expected: bool):
        offer = make_offer(spot=offer_spot)

        assert matches(offer, make_requirements(spot=required_spot)) is expected

    @pytest.mark.parametrize(
        ["offer_arch", "required_arch", "expected"],
        [
            pytest.param(None, None, True, id="any-unset"),
            pytest.param(ARM, None, True, id="any-arm"),
            pytest.param(X86, "x86", True, id="x86-x86"),
            pytest.param(None, "x86", True, id="unset-offer-arch-is-x86"),
            pytest.param(ARM, "arm", True, id="arm-arm"),
            pytest.param(X86, "arm", False, id="arm-required-x86-offer"),
            pytest.param(None, "arm", False, id="arm-required-unset-offer-arch"),
            pytest.param(ARM, "x86", False, id="x86-required-arm-offer"),
        ],
    )
    def test_cpu_arch(
        self,
        offer_arch: Optional[gpuhunt.CPUArchitecture],
        required_arch: Optional[str],
        expected: bool,
    ):
        offer = make_offer(cpu_arch=offer_arch)
        requirements = make_requirements({"cpu": {"arch": required_arch}})

        assert matches(offer, requirements) is expected

    @pytest.mark.parametrize(
        ["cpus", "required_cpus", "expected"],
        [
            pytest.param(4, "4..16", True, id="equal-to-min"),
            pytest.param(16, "4..16", True, id="equal-to-max"),
            pytest.param(2, "4..16", False, id="below-min"),
            pytest.param(32, "4..16", False, id="above-max"),
            pytest.param(1, "..8", True, id="no-min"),
            pytest.param(1, None, False, id="below-default-min"),
        ],
    )
    def test_cpu_count(self, cpus: int, required_cpus: Optional[str], expected: bool):
        offer = make_offer(cpus=cpus)
        resources = {} if required_cpus is None else {"cpu": required_cpus}

        assert matches(offer, make_requirements(resources)) is expected

    @pytest.mark.parametrize(
        ["memory_mib", "required_memory", "expected"],
        [
            pytest.param(16 * 1024, "16GB..64GB", True, id="equal-to-min"),
            pytest.param(64 * 1024, "16GB..64GB", True, id="equal-to-max"),
            pytest.param(8 * 1024, "16GB..64GB", False, id="below-min"),
            pytest.param(128 * 1024, "16GB..64GB", False, id="above-max"),
            pytest.param(512, "0.5GB..", True, id="fractional-equal-to-min"),
            pytest.param(511, "0.5GB..", False, id="fractional-below-min"),
            pytest.param(4 * 1024, None, False, id="below-default-min"),
        ],
    )
    def test_memory(self, memory_mib: int, required_memory: Optional[str], expected: bool):
        offer = make_offer(memory_mib=memory_mib)
        resources = {} if required_memory is None else {"memory": required_memory}

        assert matches(offer, make_requirements(resources)) is expected

    def test_no_gpu_spec_matches_cpu_and_gpu_offers(self):
        requirements = make_requirements({"gpu": None})

        assert matches(CPU_ONLY, requirements)
        assert matches(A100, requirements)

    def test_zero_gpus_required_matches_only_cpu_offers(self):
        requirements = make_requirements({"gpu": 0})

        assert matches(CPU_ONLY, requirements)
        assert not matches(A100, requirements)

    def test_at_least_one_gpu_required_matches_only_gpu_offers(self):
        requirements = make_requirements({"gpu": "1.."})

        assert not matches(CPU_ONLY, requirements)
        assert matches(A100, requirements)

    @pytest.mark.parametrize(
        ["gpu_count", "expected"],
        [
            pytest.param(1, False, id="below-min"),
            pytest.param(2, True, id="equal-to-min"),
            pytest.param(4, True, id="equal-to-max"),
            pytest.param(8, False, id="above-max"),
        ],
    )
    def test_gpu_count(self, gpu_count: int, expected: bool):
        offer = make_offer(gpu_count=gpu_count)

        assert matches(offer, make_requirements({"gpu": "2..4"})) is expected

    def test_gpu_spec_applies_to_cpu_offers_if_min_count_is_zero_but_not_unset(self):
        # With `count.min == 0`, GPU constraints are not checked for offers without GPUs.
        # With `count.min` unset, they are: an offer without GPUs has no vendor or name
        # and has 0 GPU memory.
        assert matches(CPU_ONLY, make_requirements({"gpu": {"vendor": "nvidia", "count": "0.."}}))
        assert not matches(
            CPU_ONLY, make_requirements({"gpu": {"vendor": "nvidia", "count": "..8"}})
        )
        assert matches(CPU_ONLY, make_requirements({"gpu": {"memory": "24GB..", "count": "0.."}}))
        assert not matches(
            CPU_ONLY, make_requirements({"gpu": {"memory": "24GB..", "count": "..8"}})
        )
        assert matches(CPU_ONLY, make_requirements({"gpu": {"count": "..8"}}))

    def test_gpu_name_matches(self):
        requirements = make_requirements({"gpu": "A100"})

        assert matches(A100, requirements)
        assert not matches(make_offer(gpu_count=1, gpu_name="H100"), requirements)

    def test_gpu_name_implies_at_least_one_gpu(self):
        assert not matches(CPU_ONLY, make_requirements({"gpu": "A100"}))

    def test_gpu_name_with_zero_min_count_matches_cpu_offers(self):
        requirements = make_requirements({"gpu": {"name": ["A100"], "count": "0.."}})

        assert matches(CPU_ONLY, requirements)
        assert not matches(make_offer(gpu_count=1, gpu_name="H100"), requirements)

    def test_gpu_name_matches_any_in_list(self):
        requirements = make_requirements({"gpu": "A100,H100"})

        assert matches(A100, requirements)
        assert matches(make_offer(gpu_count=1, gpu_name="H100"), requirements)
        assert not matches(make_offer(gpu_count=1, gpu_name="T4"), requirements)

    @pytest.mark.parametrize(
        ("offer_name", "required_name"),
        [("A100", "a100"), ("a100", "A100")],
    )
    def test_gpu_name_match_is_case_insensitive(self, offer_name: str, required_name: str):
        offer = make_offer(gpu_count=1, gpu_name=offer_name)

        assert matches(offer, make_requirements({"gpu": required_name}))

    def test_empty_gpu_name_list_matches_no_gpu_offers(self):
        requirements = make_requirements({"gpu": {"name": [], "count": "0.."}})

        assert matches(CPU_ONLY, requirements)
        assert not matches(A100, requirements)

    def test_gpu_vendor(self):
        requirements = make_requirements({"gpu": "amd"})

        assert matches(make_offer(gpu_count=1, gpu_name="MI300X", gpu_vendor=AMD), requirements)
        assert not matches(A100, requirements)
        assert not matches(CPU_ONLY, requirements)

    def test_tpu_vendor(self):
        offer = make_offer(gpu_count=1, gpu_name="v5litepod-8", gpu_vendor=GOOGLE)

        assert matches(offer, make_requirements({"gpu": "tpu"}))
        assert not matches(offer, make_requirements({"gpu": "nvidia"}))

    @pytest.mark.parametrize(
        ["gpu_memory_gib", "expected"],
        [
            pytest.param(40, True, id="equal-to-min"),
            pytest.param(80, True, id="equal-to-max"),
            pytest.param(24, False, id="below-min"),
            pytest.param(141, False, id="above-max"),
        ],
    )
    def test_gpu_memory(self, gpu_memory_gib: int, expected: bool):
        offer = make_offer(gpu_count=1, gpu_memory_gib=gpu_memory_gib)

        assert matches(offer, make_requirements({"gpu": "40GB..80GB"})) is expected

    def test_gpu_memory_is_per_gpu(self):
        offer = make_offer(gpu_count=8, gpu_memory_gib=24)

        assert not matches(offer, make_requirements({"gpu": "40GB.."}))

    @pytest.mark.parametrize(
        ["gpu_count", "expected"],
        [
            pytest.param(1, False, id="below-min"),
            pytest.param(2, True, id="equal-to-min"),
            pytest.param(8, True, id="above-min"),
        ],
    )
    def test_gpu_total_memory(self, gpu_count: int, expected: bool):
        offer = make_offer(gpu_count=gpu_count, gpu_memory_gib=80)
        requirements = make_requirements({"gpu": {"total_memory": "160GB.."}})

        assert matches(offer, requirements) is expected

    @pytest.mark.parametrize(
        ["gpu_name", "gpu_vendor", "expected"],
        [
            pytest.param("A100", NVIDIA, True, id="equal"),  # 8.0
            pytest.param("H100", NVIDIA, True, id="higher"),  # 9.0
            pytest.param("T4", NVIDIA, False, id="lower"),  # 7.5
            pytest.param("a100", NVIDIA, True, id="name-case-insensitive"),
            pytest.param("UnknownGPU", NVIDIA, False, id="unknown-name"),
            pytest.param("MI300X", AMD, False, id="non-nvidia"),
        ],
    )
    def test_gpu_compute_capability(
        self, gpu_name: str, gpu_vendor: gpuhunt.AcceleratorVendor, expected: bool
    ):
        offer = make_offer(gpu_count=1, gpu_name=gpu_name, gpu_vendor=gpu_vendor)
        requirements = make_requirements({"gpu": {"compute_capability": "8.0"}})

        assert matches(offer, requirements) is expected

    @pytest.mark.parametrize(
        ["disk_gib", "required_disk", "check_disk", "expected"],
        [
            pytest.param(150, "100GB..200GB", True, True, id="within-range"),
            pytest.param(50, "100GB..", True, False, id="below-min"),
            pytest.param(300, "..200GB", True, False, id="above-max"),
            # A real 0 GB disk would fail the min bound, so a match proves that
            # the requirement is ignored for offers with unknown disk size.
            pytest.param(0, "100GB..200GB", True, True, id="unknown-size"),
            pytest.param(50, None, True, False, id="below-default-min"),
            pytest.param(50, "100GB..", False, True, id="check-disk-disabled"),
        ],
    )
    def test_disk(
        self, disk_gib: int, required_disk: Optional[str], check_disk: bool, expected: bool
    ):
        offer = make_offer(disk_gib=disk_gib)
        resources = {} if required_disk is None else {"disk": required_disk}

        assert matches(offer, make_requirements(resources), check_disk=check_disk) is expected

    def test_no_disk_spec_matches_any_disk(self):
        offer = make_offer(disk_gib=1)

        assert matches(offer, Requirements(resources=ResourcesSpec(disk=None)))

    def test_all_constraints_match(self):
        offer = make_offer(
            price=10.0,
            spot=True,
            cpu_arch=X86,
            cpus=96,
            memory_mib=1024 * 1024,
            gpu_count=8,
            gpu_name="H100",
            gpu_memory_gib=80,
            disk_gib=500,
        )
        requirements = make_requirements(
            {
                "cpu": "x86:64..",
                "memory": "512GB..",
                "gpu": {
                    "vendor": "nvidia",
                    "name": ["H100"],
                    "count": 8,
                    "memory": "80GB",
                    "total_memory": "640GB..",
                    "compute_capability": "9.0",
                },
                "disk": "200GB..",
            },
            spot=True,
            max_price=20.0,
        )

        assert matches(offer, requirements)


class TestOfferDiskFitter:
    def test_sets_min_disk_size_within_configurable_and_required_ranges(self):
        offer = get_instance_offer_with_availability(gpu_count=1, disk_gib=100)
        requirements = Requirements(resources=ResourcesSpec.model_validate({"disk": "200GB.."}))
        fitter = OfferDiskFitter(requirements)

        fitted_a = fitter.fit(offer, Range[Memory](min=Memory.parse("10GB"), max=None))
        fitted_b = fitter.fit(offer, Range[Memory](min=Memory.parse("300GB"), max=None))
        fitted_c = fitter.fit(offer, Range[Memory](min=Memory.parse("10GB"), max=None))

        assert fitted_a is not None and fitted_b is not None and fitted_c is not None
        assert fitted_a.instance.resources.disk == Disk(size_mib=200 * 1024)
        assert fitted_b.instance.resources.disk == Disk(size_mib=300 * 1024)
        assert fitted_c.instance.resources.disk is fitted_a.instance.resources.disk
        assert fitted_a.instance.resources.gpus is offer.instance.resources.gpus
        assert offer.instance.resources.disk == Disk(size_mib=100 * 1024)

    def test_uses_default_disk_if_requirements_have_no_disk(self):
        offer = get_instance_offer_with_availability(disk_gib=1)
        requirements = Requirements(resources=ResourcesSpec(disk=None))
        configurable = Range[Memory](min=Memory.parse("10GB"), max=None)

        fitted = OfferDiskFitter(requirements).fit(offer, configurable)

        assert fitted is not None
        assert fitted.instance.resources.disk == Disk(size_mib=100 * 1024)

    def test_returns_none_if_configurable_range_does_not_fit(self):
        offer = get_instance_offer_with_availability()
        requirements = Requirements(resources=ResourcesSpec.model_validate({"disk": "..50GB"}))
        configurable = Range[Memory](min=Memory.parse("100GB"), max=None)

        assert OfferDiskFitter(requirements).fit(offer, configurable) is None

    def test_returns_same_offer_if_disk_size_unchanged(self):
        offer = get_instance_offer_with_availability(disk_gib=100)
        requirements = Requirements(resources=ResourcesSpec.model_validate({"disk": "100GB.."}))
        configurable = Range[Memory](min=Memory.parse("10GB"), max=None)

        assert OfferDiskFitter(requirements).fit(offer, configurable) is offer

    @pytest.mark.parametrize(
        ["disk_gib", "required_disk", "fits"],
        [
            pytest.param(150, "100GB..200GB", True, id="within-range"),
            pytest.param(50, "100GB..", False, id="below-min"),
            pytest.param(300, "..200GB", False, id="above-max"),
            pytest.param(0, "100GB..200GB", True, id="unknown-size"),
            pytest.param(50, None, True, id="no-disk-requirement"),
        ],
    )
    def test_checks_fixed_disk(self, disk_gib: int, required_disk: Optional[str], fits: bool):
        offer = get_instance_offer_with_availability(disk_gib=disk_gib)
        requirements = Requirements(
            resources=ResourcesSpec.model_validate({"disk": required_disk})
        )

        fitted = OfferDiskFitter(requirements).fit(offer, None)

        assert fitted is (offer if fits else None)
