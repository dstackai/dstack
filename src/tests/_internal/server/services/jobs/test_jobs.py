from unittest.mock import patch

import pytest

import dstack._internal.server.settings as server_settings
from dstack._internal.core.models.common import RegistryAuth
from dstack._internal.core.models.configurations import TaskConfiguration
from dstack._internal.core.models.profiles import Profile
from dstack._internal.core.models.repos.local import LocalRunRepoData
from dstack._internal.core.models.runs import RunSpec
from dstack._internal.server.services.docker import ImageConfig
from dstack._internal.server.services.jobs import get_job_specs_from_run_spec


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
            # Setting `commands` and `user` is a known hack that we advertised to some customers
            # to avoid registry requests.
            TaskConfiguration(image="ubuntu", commands=["sleep infinity"], user="root"),
            0,
            id="custom-image-with-commands-and-user",
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
    fake_image_config = ImageConfig.parse_obj({"Entrypoint": ["/bin/bash"]})
    with patch(
        "dstack._internal.server.services.jobs.configurators.base._get_image_config",
        return_value=fake_image_config,
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
    fake_image_config = ImageConfig.parse_obj({"Entrypoint": ["/bin/bash"]})
    with patch(
        "dstack._internal.server.services.jobs.configurators.base._get_image_config",
        return_value=fake_image_config,
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
