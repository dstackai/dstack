import re
from typing import Optional
from unittest.mock import MagicMock

import gpuhunt
import pytest

from dstack._internal.core.backends.base.compute import (
    ComputeWithCreateInstanceSupport,
    GoArchType,
    generate_unique_backend_name,
    generate_unique_gateway_instance_name,
    generate_unique_instance_name,
    generate_unique_volume_name,
    normalize_arch,
)
from dstack._internal.core.models.instances import InstanceConfiguration
from dstack._internal.core.models.resources import CPUSpec, ResourcesSpec
from dstack._internal.core.models.runs import Requirements
from dstack._internal.server.testing.common import (
    get_gateway_compute_configuration,
    get_instance_configuration,
    get_volume,
)


class _FakeCreateInstanceCompute(ComputeWithCreateInstanceSupport):
    """Minimal Compute stub that just records the `InstanceConfiguration` it was given."""

    last_instance_config: Optional[InstanceConfiguration] = None

    def create_instance(self, instance_offer, instance_config, placement_group):
        self.last_instance_config = instance_config
        # `run_job()`'s return value isn't exercised by this test - it's returned
        # as-is by `create_instance`, with no validation in `run_job()` itself.
        return MagicMock()


class TestRunJobSourcesFromEffectiveRequirements:
    """
    `run_job()` is called with an already fleet+run-combined `Requirements` object
    (see `_get_effective_profile_and_requirements` /
    `get_run_profile_and_requirements_in_fleet` in
    `server/background/pipeline_tasks/jobs_submitted.py`). It must build the
    `InstanceConfiguration` from that `requirements` parameter, not from
    `job.job_spec.requirements`, which only ever reflects the run's own
    requirements as computed at submission time and is never updated to include
    a fleet's `reservation`/`security_group` when a run provisions new capacity
    into an existing fleet.
    """

    def _resources(self) -> ResourcesSpec:
        return ResourcesSpec(cpu=CPUSpec.parse("1"))

    def _run_job(self, effective_requirements: Requirements):
        compute = _FakeCreateInstanceCompute()
        run = MagicMock()
        run.project_name = "test-project"
        run.user = "test-user"
        run.run_spec.merged_profile.tags = None
        job = MagicMock()
        job.job_spec.job_name = "test-run-0-0"
        # The job's own (run-only) requirements deliberately differ from the
        # effective (fleet+run-combined) ones passed as the `requirements` arg,
        # to prove which one `run_job` actually uses.
        job.job_spec.requirements = Requirements(
            resources=self._resources(),
            reservation="job-spec-reservation",
            security_group="job-spec-security-group",
        )
        instance_offer = MagicMock()
        instance_offer.region = "us-east-1"
        instance_offer.price = 1.0
        instance_offer.copy.return_value = instance_offer
        compute.run_job(
            run=run,
            job=job,
            instance_offer=instance_offer,
            project_ssh_public_key="ssh-rsa AAAA",
            project_ssh_private_key="private-key",
            volumes=[],
            placement_group=None,
            requirements=effective_requirements,
        )
        assert compute.last_instance_config is not None
        return compute.last_instance_config

    def test_uses_effective_reservation_not_job_spec_reservation(self):
        effective_requirements = Requirements(
            resources=self._resources(), reservation="fleet-reservation"
        )
        instance_config = self._run_job(effective_requirements)
        assert instance_config.reservation == "fleet-reservation"

    def test_uses_effective_security_group_not_job_spec_security_group(self):
        effective_requirements = Requirements(
            resources=self._resources(), security_group="fleet-security-group"
        )
        instance_config = self._run_job(effective_requirements)
        assert instance_config.security_group == "fleet-security-group"

    def test_none_in_effective_requirements_is_respected(self):
        # Even though job.job_spec.requirements sets both fields, an effective
        # Requirements with neither set must result in neither being used -
        # confirming `run_job` isn't merging the two, just using `requirements`.
        effective_requirements = Requirements(resources=self._resources())
        instance_config = self._run_job(effective_requirements)
        assert instance_config.reservation is None
        assert instance_config.security_group is None


class TestGenerateUniqueInstanceName:
    def test_generates_name(self):
        configuration = get_instance_configuration(
            project_name="project1", instance_name="my-instance"
        )
        name = generate_unique_instance_name(configuration, 60)
        assert re.match(r"^dstack-project1-my-instance-[a-z0-9]{8}$", name)


class TestGenerateUniqueGatewayInstanceName:
    def test_generates_name(self):
        configuration = get_gateway_compute_configuration(
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
