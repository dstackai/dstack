from unittest.mock import patch

import gpuhunt
import pytest

import dstack._internal.server.settings as server_settings
from dstack._internal.core.models.common import RegistryAuth
from dstack._internal.core.models.configurations import TaskConfiguration
from dstack._internal.core.models.profiles import Profile
from dstack._internal.core.models.repos.local import LocalRunRepoData
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.runs import JobSpec, RunSpec
from dstack._internal.server.services.docker import ImageConfig
from dstack._internal.server.services.jobs import (
    get_job_specs_from_run_spec,
    job_spec_updatable_in_place,
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
