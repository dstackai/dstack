import re
from typing import Optional

import gpuhunt
import pytest

from dstack._internal import settings
from dstack._internal.core.backends.base.compute import (
    ComputeWithAllOffersCached,
    GoArchType,
    generate_unique_backend_name,
    generate_unique_gateway_instance_name,
    generate_unique_instance_name,
    generate_unique_volume_name,
    get_dstack_gateway_install_command,
    normalize_arch,
    parse_provider_ref_from_name,
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
from tests._internal.core.backends.base.gateway_host import GatewayHost, get_install_script_var


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
        requirements = Requirements(
            resources=ResourcesSpec.model_validate({"gpu": 1, "disk": "200GB.."})
        )

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
        requirements = Requirements(resources=ResourcesSpec.model_validate({"disk": "200GB.."}))

        offers = list(compute.get_offers(requirements, False, False))

        assert [o.instance.name for o in offers] == ["configurable"]


class TestGenerateUniqueInstanceName:
    def test_generates_name(self):
        configuration = get_instance_configuration(
            project_name="project1", instance_name="my-instance"
        )
        name = generate_unique_instance_name(configuration, 60)
        assert re.match(r"^dstack-project1-my-instance-[a-z0-9]{8}$", name)

    def test_generates_name_with_provider_ref(self):
        configuration = get_instance_configuration(
            project_name="project1", instance_name="my-instance"
        )
        configuration.provider_ref = "abc123def456"
        name = generate_unique_instance_name(configuration, 60, with_provider_ref=True)
        assert re.match(r"^dstack-project1-my-instance-abc123def456[a-z0-9]{4}$", name)

    def test_ignores_provider_ref_by_default(self):
        configuration = get_instance_configuration(
            project_name="project1", instance_name="my-instance"
        )
        configuration.provider_ref = "abc123def456"
        name = generate_unique_instance_name(configuration, 60)
        assert re.match(r"^dstack-project1-my-instance-[a-z0-9]{8}$", name)

    def test_falls_back_to_random_suffix_without_provider_ref(self):
        configuration = get_instance_configuration(
            project_name="project1", instance_name="my-instance"
        )
        name = generate_unique_instance_name(configuration, 60, with_provider_ref=True)
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

    def test_strips_trailing_hyphens_of_truncated_prefix(self):
        name = generate_unique_backend_name("batch-inference", "acme-corp-production-us-east", 40)
        assert re.match(r"^dstack-acme-corp-production-us-[a-z0-9]{8}$", name)

    def test_validates_project_name(self):
        name = generate_unique_backend_name("instance", "invalid_project!@", 60)
        assert re.match(r"^dstack-instance-[a-z0-9]{8}$", name)

    def test_generates_name_with_provider_ref(self):
        name = generate_unique_backend_name("instance", "project", 60, "abc123def456")
        assert re.match(r"^dstack-project-instance-abc123def456[a-z0-9]{4}$", name)

    def test_truncates_prefix_but_keeps_provider_ref(self):
        name = generate_unique_backend_name("a" * 100, "project", 40, "abc123def456")
        assert len(name) == 40
        assert re.match(r"^dstack-project-aaaaaaaa-abc123def456[a-z0-9]{4}$", name)


class TestParseProviderRefFromName:
    @pytest.mark.parametrize(
        ("project_name", "max_length"),
        [("project", 60), (None, 60), ("project", 24)],
    )
    def test_parses_generated_name(self, project_name: Optional[str], max_length: int):
        name = generate_unique_backend_name("instance", project_name, max_length, "abc123def456")
        assert parse_provider_ref_from_name(name) == "abc123def456"

    @pytest.mark.parametrize(
        "name",
        [
            "dstack-project-instance-1a2b3c4d",  # name without provider_ref
            "dstack-project-instance-abc123def456",  # no random suffix
            "dstack-project-instance-ABC123DEF456abcd",  # uppercase
            "other-project-instance-abc123def456abcd",  # not a dstack name
            "dstack-project-instance-abc123def456abcd-data",  # unstripped internal suffix
        ],
    )
    def test_returns_none_for_names_without_provider_ref(self, name: str):
        assert parse_provider_ref_from_name(name) is None


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


_UV_VERSION = get_install_script_var("uv_version")
_PYTHON_VERSION = get_install_script_var("python_version")
_UV_URL = (
    f"https://github.com/astral-sh/uv/releases/download/{_UV_VERSION}"
    "/uv-x86_64-unknown-linux-musl.tar.gz"
)


@pytest.mark.docker
class TestGetDstackGatewayInstallCommand:
    @pytest.fixture(autouse=True)
    def gateway_package(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(settings, "DSTACK_GATEWAY_PACKAGE_URL", None)
        monkeypatch.setattr(settings, "DSTACK_VERSION", "0.22.3")

    def test_installs_on_fresh_host(self, gateway_host: GatewayHost):
        result = gateway_host.run(get_dstack_gateway_install_command())

        assert result.returncode == 0, result.stderr
        assert "Update successfully completed" in result.stdout
        assert gateway_host.active_venv() == "green"
        assert gateway_host.events() == [
            f"wget {_UV_URL}",
            f"uv python install {_PYTHON_VERSION}",
            f"uv venv --managed-python --seed --python {_PYTHON_VERSION} /home/ubuntu/dstack/green",
            "uv pip install --python /home/ubuntu/dstack/green/bin/python"
            " --refresh-package dstack dstack[gateway]==0.22.3",
            "green python -m dstack._internal.proxy.gateway.systemd install",
            "systemctl daemon-reload active=green",
            "systemctl restart dstack.gateway active=green",
        ]

    def test_skips_if_build_and_python_match(self, gateway_host: GatewayHost):
        gateway_host.add_venv("blue", installed=f"{_PYTHON_VERSION} 0.22.3", active=True)

        result = gateway_host.run(get_dstack_gateway_install_command())

        assert result.returncode == 0, result.stderr
        assert "Skipping" in result.stdout
        assert gateway_host.active_venv() == "blue"
        assert gateway_host.events() == ["blue python -c"]

    @pytest.mark.parametrize(
        "installed",
        [
            pytest.param("3.10 0.22.3", id="outdated-python"),
            pytest.param(f"{_PYTHON_VERSION} 0.22.2", id="outdated-build"),
            pytest.param(None, id="broken-venv"),
        ],
    )
    def test_recreates_inactive_venv_and_switches_to_it(
        self, gateway_host: GatewayHost, installed: Optional[str]
    ):
        gateway_host.add_venv("blue", installed=installed, active=True)
        gateway_host.add_venv("green", installed="3.10 0.22.1")
        gateway_host.add_uv(_UV_VERSION)

        result = gateway_host.run(get_dstack_gateway_install_command())

        assert result.returncode == 0, result.stderr
        assert gateway_host.active_venv() == "green"
        assert not gateway_host.exists("/home/ubuntu/dstack/green/installed")
        assert gateway_host.events() == [
            "blue python -c",
            "uv --version",
            f"uv python install {_PYTHON_VERSION}",
            f"uv venv --managed-python --seed --python {_PYTHON_VERSION} /home/ubuntu/dstack/green",
            "uv pip install --python /home/ubuntu/dstack/green/bin/python"
            " --refresh-package dstack dstack[gateway]==0.22.3",
            "green python -m dstack._internal.proxy.gateway.systemd install",
            "systemctl daemon-reload active=green",
            "systemctl restart dstack.gateway active=green",
        ]

    def test_never_skips_unversioned_package(
        self, gateway_host: GatewayHost, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(settings, "DSTACK_GATEWAY_PACKAGE_URL", "https://example.com/d.whl")
        gateway_host.add_venv("green", installed=f"{_PYTHON_VERSION} 0.22.3", active=True)
        gateway_host.add_uv(_UV_VERSION)

        result = gateway_host.run(get_dstack_gateway_install_command())

        assert result.returncode == 0, result.stderr
        assert gateway_host.active_venv() == "blue"
        events = gateway_host.events()
        assert "green python -c" not in events
        assert (
            "uv pip install --python /home/ubuntu/dstack/blue/bin/python"
            " --refresh-package dstack dstack[gateway] @ https://example.com/d.whl"
        ) in events

    def test_replaces_outdated_uv(self, gateway_host: GatewayHost):
        gateway_host.add_venv("blue", installed="3.10 0.22.2", active=True)
        gateway_host.add_uv("0.1.0")

        result = gateway_host.run(get_dstack_gateway_install_command())

        assert result.returncode == 0, result.stderr
        assert gateway_host.events()[1:4] == [
            "uv --version",
            f"wget {_UV_URL}",
            f"uv python install {_PYTHON_VERSION}",
        ]
        assert gateway_host.uv_version() == _UV_VERSION

    def test_keeps_active_venv_if_install_fails(self, gateway_host: GatewayHost):
        gateway_host.add_venv("blue", installed="3.10 0.22.2", active=True)
        gateway_host.add_uv(_UV_VERSION, fail_on="pip")

        result = gateway_host.run(get_dstack_gateway_install_command())

        assert result.returncode != 0
        assert "Update successfully completed" not in result.stdout
        assert gateway_host.active_venv() == "blue"
        assert not any(e.startswith("systemctl") for e in gateway_host.events())
