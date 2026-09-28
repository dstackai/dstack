from unittest.mock import patch

import gpuhunt
import pytest

import dstack._internal.server.settings as server_settings
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import RegistryAuth
from dstack._internal.core.models.configurations import TaskConfiguration
from dstack._internal.core.models.profiles import Profile
from dstack._internal.core.models.repos.local import LocalRunRepoData
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.runs import JobSpec, RunSpec
from dstack._internal.core.models.volumes import DaytonaVolumeConfiguration
from dstack._internal.server.services.docker import ImageConfig
from dstack._internal.server.services.jobs import (
    _get_job_mount_point_attached_volume,
    get_job_specs_from_run_spec,
    job_spec_updatable_in_place,
)
from dstack._internal.server.testing.common import (
    get_job_provisioning_data,
    get_volume,
    get_volume_configuration,
    get_volume_provisioning_data,
)


@pytest.mark.parametrize(
    "configuration, expected_calls",
    [
        pytest.param(
            # No need to request the registry if our default image is used.
            TaskConfiguration(commands=["sleep infinity"]),
            0,
            id="default-dstack-image",
        ),
        pytest.param(
            TaskConfiguration(image="ubuntu"),
            1,
            id="custom-image",
        ),
        pytest.param(
            TaskConfiguration(image="ubuntu", commands=["sleep infinity"]),
            1,
            id="custom-image-with-commands",
        ),
        pytest.param(
            TaskConfiguration(image="ubuntu", user="root"),
            1,
            id="custom-image-with-user",
        ),
        pytest.param(
            # `commands` and `user` cover the image config, but the registry is still requested
            # to find out which CPU architectures the image supports.
            TaskConfiguration(image="ubuntu", commands=["sleep infinity"], user="root"),
            1,
            id="custom-image-with-commands-and-user",
        ),
        pytest.param(
            # Setting `commands`, `user`, and `resources.cpu.arch` is a known hack that we
            # advertised to some customers to avoid registry requests.
            TaskConfiguration(
                image="ubuntu",
                commands=["sleep infinity"],
                user="root",
                resources=ResourcesSpec.model_validate({"cpu": "x86:2"}),
            ),
            0,
            id="custom-image-with-commands-user-and-arch",
        ),
    ],
)
@pytest.mark.asyncio
async def test_get_job_specs_from_run_spec_image_config_calls(
    configuration: TaskConfiguration, expected_calls: int
) -> None:
    """
    Test the number of times we attempt to fetch the image config from the Docker registry.

    Whenever possible, we prefer not to request the registry to avoid hitting rate limits.
    """

    run_spec = RunSpec(
        run_name="test-run",
        repo_data=LocalRunRepoData(repo_dir="/"),
        configuration=configuration,
        profile=Profile(name="default"),
        ssh_key_pub="user_ssh_key",
    )
    fake_image_config = ImageConfig.model_validate({"Entrypoint": ["/bin/bash"]})
    with patch(
        "dstack._internal.server.services.jobs.configurators.base"
        "._get_image_config_and_cpu_architectures",
        return_value=(fake_image_config, {gpuhunt.CPUArchitecture.X86}),
    ) as mock_get_image_config:
        await get_job_specs_from_run_spec(run_spec=run_spec, secrets={}, replica_num=0)
        assert mock_get_image_config.call_count == expected_calls


@pytest.mark.asyncio
async def test_get_image_config_uses_server_default_registry(monkeypatch) -> None:
    monkeypatch.setattr(server_settings, "SERVER_DEFAULT_DOCKER_REGISTRY", "registry.example")
    monkeypatch.setattr(server_settings, "SERVER_DEFAULT_DOCKER_REGISTRY_USERNAME", "user")
    monkeypatch.setattr(server_settings, "SERVER_DEFAULT_DOCKER_REGISTRY_PASSWORD", "pass")
    run_spec = RunSpec(
        run_name="test-run",
        repo_data=LocalRunRepoData(repo_dir="/"),
        configuration=TaskConfiguration(image="ubuntu"),
        profile=Profile(name="default"),
        ssh_key_pub="user_ssh_key",
    )
    fake_image_config = ImageConfig.model_validate({"Entrypoint": ["/bin/bash"]})
    with patch(
        "dstack._internal.server.services.jobs.configurators.base"
        "._get_image_config_and_cpu_architectures",
        return_value=(fake_image_config, {gpuhunt.CPUArchitecture.X86}),
    ) as mock_get_image_config:
        job_specs = await get_job_specs_from_run_spec(run_spec=run_spec, secrets={}, replica_num=0)
        mock_get_image_config.assert_called_once_with(
            "registry.example/ubuntu",
            RegistryAuth(username="user", password="pass"),
        )

    assert len(job_specs) == 1
    # NOTE: server defaults should not be set on the job spec,
    # especially the credentials, so as not to leak them in the API.
    assert job_specs[0].image_name == "ubuntu"
    assert job_specs[0].registry_auth is None


class TestJobSpecUpdatableInPlace:
    def _job_spec(self, **requirements_overrides) -> JobSpec:
        resources = {"cpu": {"count": 2}, **requirements_overrides}
        return JobSpec(
            job_num=0,
            job_name="test-run-0-0",
            commands=["sleep infinity"],
            env={},
            image_name="ubuntu",
            requirements={"resources": resources},
        )

    def test_identical_specs(self):
        assert job_spec_updatable_in_place(self._job_spec(), self._job_spec())

    def test_unrelated_change(self):
        old_job_spec = self._job_spec()
        new_job_spec = self._job_spec()
        new_job_spec.commands = ["sleep 10"]

        assert not job_spec_updatable_in_place(old_job_spec, new_job_spec)

    def test_arch_widened_to_any(self):
        # A job submitted by an older server that always resolved `cpu.arch`
        old_job_spec = self._job_spec(cpu={"arch": gpuhunt.CPUArchitecture.X86, "count": 2})
        new_job_spec = self._job_spec(cpu={"arch": None, "count": 2})

        assert job_spec_updatable_in_place(old_job_spec, new_job_spec)

    def test_arch_widened_to_any_with_another_change(self):
        old_job_spec = self._job_spec(cpu={"arch": gpuhunt.CPUArchitecture.X86, "count": 2})
        new_job_spec = self._job_spec(cpu={"arch": None, "count": 2})
        new_job_spec.commands = ["sleep 10"]

        assert not job_spec_updatable_in_place(old_job_spec, new_job_spec)

    def test_arch_narrowed_to_specific(self):
        old_job_spec = self._job_spec(cpu={"arch": None, "count": 2})
        new_job_spec = self._job_spec(cpu={"arch": gpuhunt.CPUArchitecture.X86, "count": 2})

        assert not job_spec_updatable_in_place(old_job_spec, new_job_spec)

    def test_arch_changed_to_another_specific(self):
        old_job_spec = self._job_spec(cpu={"arch": gpuhunt.CPUArchitecture.X86, "count": 2})
        new_job_spec = self._job_spec(cpu={"arch": gpuhunt.CPUArchitecture.ARM, "count": 2})

        assert not job_spec_updatable_in_place(old_job_spec, new_job_spec)

    def test_does_not_mutate_the_new_spec(self):
        old_job_spec = self._job_spec(cpu={"arch": gpuhunt.CPUArchitecture.X86, "count": 2})
        new_job_spec = self._job_spec(cpu={"arch": None, "count": 2})

        job_spec_updatable_in_place(old_job_spec, new_job_spec)

        assert new_job_spec.requirements.resources.cpu.arch is None


class TestGetJobMountPointAttachedVolume:
    @pytest.mark.parametrize(("region", "gpu_count"), [("us", 0), ("earth", 1)])
    def test_global_volume_matches_cpu_and_gpu_regions(self, region, gpu_count):
        volume = get_volume(configuration=DaytonaVolumeConfiguration())
        other_backend_volume = get_volume(
            configuration=get_volume_configuration(backend=BackendType.AWS, region=region)
        )
        provisioning_data = get_job_provisioning_data(
            backend=BackendType.DAYTONA, region=region, gpu_count=gpu_count
        )

        assert (
            _get_job_mount_point_attached_volume([other_backend_volume, volume], provisioning_data)
            == volume
        )

    def test_regional_volume_preserves_region_and_zone_matching(self):
        volumes = [
            get_volume(
                configuration=get_volume_configuration(backend=BackendType.AWS, region=region),
                provisioning_data=get_volume_provisioning_data(availability_zone=zone),
            )
            for region, zone in [
                ("eu-west-1", "eu-west-1a"),
                ("us-east-1", "us-east-1b"),
                ("us-east-1", "us-east-1a"),
            ]
        ]
        provisioning_data = get_job_provisioning_data(
            backend=BackendType.AWS, region="US-EAST-1", availability_zone="US-EAST-1A"
        )

        assert _get_job_mount_point_attached_volume(volumes, provisioning_data) == volumes[2]
