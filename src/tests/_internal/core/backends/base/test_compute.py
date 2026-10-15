import re
from typing import Optional

import gpuhunt
import pytest

from dstack._internal.core.backends.base.compute import (
    ComputeWithAllOffersCached,
    GoArchType,
    generate_unique_backend_name,
    generate_unique_gateway_instance_name,
    generate_unique_instance_name,
    generate_unique_volume_name,
    normalize_arch,
)
from dstack._internal.core.models.instances import Disk, InstanceOfferWithAvailability
from dstack._internal.core.models.resources import Memory, Range, ResourcesSpec
from dstack._internal.core.models.runs import Requirements
from dstack._internal.server.testing.common import (
    get_gateway_replica_configuration,
    get_instance_configuration,
    get_instance_offer_with_availability,
    get_volume,
)


class _ComputeWithCachedOffers(ComputeWithAllOffersCached):
    def __init__(
        self,
        offers: list[InstanceOfferWithAvailability],
        disk_size_ranges: dict[str, Optional[Range[Memory]]],
    ) -> None:
        super().__init__()
        self.offers = offers
        self.disk_size_ranges = disk_size_ranges
        self.disk_size_range_calls: list[InstanceOfferWithAvailability] = []

    def get_all_offers_with_availability(
        self, unallocated_resources: bool
    ) -> list[InstanceOfferWithAvailability]:
        return self.offers

    def get_offer_disk_size_range(
        self, offer: InstanceOfferWithAvailability
    ) -> Optional[Range[Memory]]:
        self.disk_size_range_calls.append(offer)
        return self.disk_size_ranges[offer.instance.name]


class TestComputeWithAllOffersCachedGetOffers:
    def test_fits_disk_only_for_offers_matching_other_requirements(self):
        gpu_offer = get_instance_offer_with_availability(
            instance_type="gpu", gpu_count=1, disk_gib=100
        )
        cpu_offer = get_instance_offer_with_availability(
            instance_type="cpu", gpu_count=0, disk_gib=100
        )
        configurable = Range[Memory](min=Memory.parse("50GB"), max=None)
        compute = _ComputeWithCachedOffers(
            [gpu_offer, cpu_offer], {"gpu": configurable, "cpu": configurable}
        )
        requirements = Requirements(resources=ResourcesSpec(gpu=1, disk="200GB.."))

        offers = list(compute.get_offers(requirements, False, False))

        assert [o.instance.resources.disk for o in offers] == [Disk(size_mib=200 * 1024)]
        assert compute.disk_size_range_calls == [gpu_offer]
        assert gpu_offer.instance.resources.disk == Disk(size_mib=100 * 1024)

    def test_excludes_offers_whose_disk_does_not_fit(self):
        configurable_offer = get_instance_offer_with_availability(
            instance_type="configurable", disk_gib=100
        )
        fixed_offer = get_instance_offer_with_availability(instance_type="fixed", disk_gib=100)
        compute = _ComputeWithCachedOffers(
            [configurable_offer, fixed_offer],
            {"configurable": Range[Memory](min=Memory.parse("50GB"), max=None), "fixed": None},
        )
        requirements = Requirements(resources=ResourcesSpec(disk="200GB.."))

        offers = list(compute.get_offers(requirements, False, False))

        assert [o.instance.name for o in offers] == ["configurable"]


class TestGenerateUniqueInstanceName:
    def test_generates_name(self):
        configuration = get_instance_configuration(
            project_name="project1", instance_name="my-instance"
        )
        name = generate_unique_instance_name(configuration, 60)
        assert re.match(r"^dstack-project1-my-instance-[a-z0-9]{8}$", name)


class TestGenerateUniqueGatewayInstanceName:
    def test_generates_name(self):
        configuration = get_gateway_replica_configuration(
            project_name="project1", instance_name="my-gateway"
        )
        name = generate_unique_gateway_instance_name(configuration, 60)
        assert re.match(r"^dstack-project1-my-gateway-[a-z0-9]{8}$", name)


class TestGenerateUniqueVolumeName:
    def test_generates_name(self):
        volume = get_volume(project_name="project1", name="my-volume")
        name = generate_unique_volume_name(volume, 60)
        assert re.match(r"^dstack-project1-my-volume-[a-z0-9]{8}$", name)


class TestGenerateUniqueBackendName:
    def test_generates_name_with_project(self):
        name = generate_unique_backend_name("instance", "project", 60)
        assert re.match(r"^dstack-project-instance-[a-z0-9]{8}$", name)

    def test_generates_name_without_project(self):
        name = generate_unique_backend_name("instance", None, 60)
        assert re.match(r"^dstack-instance-[a-z0-9]{8}$", name)

    def test_truncates_long_names(self):
        name = generate_unique_backend_name("a" * 100, "project", 30)
        assert re.match(r"^dstack-project-aaaaaa-[a-z0-9]{8}$", name)

    def test_validates_project_name(self):
        name = generate_unique_backend_name("instance", "invalid_project!@", 60)
        assert re.match(r"^dstack-instance-[a-z0-9]{8}$", name)


class TestNormalizeArch:
    @pytest.mark.parametrize(
        "arch", [None, "", "X86", "x86_64", "AMD64", gpuhunt.CPUArchitecture.X86]
    )
    def test_amd64(self, arch: Optional[str]):
        assert normalize_arch(arch) is GoArchType.AMD64

    @pytest.mark.parametrize("arch", ["arm", "ARM64", "AArch64", gpuhunt.CPUArchitecture.ARM])
    def test_arm64(self, arch: str):
        assert normalize_arch(arch) is GoArchType.ARM64

    @pytest.mark.parametrize("arch", ["IA32", "i686", "ARM32", "aarch32"])
    def test_32bit_not_supported(self, arch: str):
        with pytest.raises(ValueError, match="32-bit architectures are not supported"):
            normalize_arch(arch)

    def test_unknown_arch(self):
        with pytest.raises(ValueError, match="Unsupported architecture: MIPS"):
            normalize_arch("MIPS")
