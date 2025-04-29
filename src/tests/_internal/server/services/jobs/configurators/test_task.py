from typing import Optional
from unittest.mock import patch

import pytest

from dstack._internal.core.models.configurations import TaskConfiguration
from dstack._internal.core.models.runs import JobSSHKey
from dstack._internal.server.services.docker import ImageConfig
from dstack._internal.server.services.jobs.configurators.task import TaskJobConfigurator
from dstack._internal.server.testing.common import get_run_spec


@pytest.mark.asyncio
@pytest.mark.usefixtures("image_config_mock")
class TestSSHKey:
    async def test_single_node(self):
        configuration = TaskConfiguration(nodes=1, image="debian")
        run_spec = get_run_spec(run_name="run", repo_id="id", configuration=configuration)
        configurator = TaskJobConfigurator(run_spec)

        job_specs = await configurator.get_job_specs(replica_num=0)

        assert len(job_specs) == 1
        assert job_specs[0].ssh_key is None

    async def test_multi_node(self):
        configuration = TaskConfiguration(nodes=2, image="debian")
        run_spec = get_run_spec(run_name="run", repo_id="id", configuration=configuration)
        configurator = TaskJobConfigurator(run_spec)

        with patch("dstack._internal.utils.crypto.generate_rsa_key_pair_bytes") as gen_mock:
            gen_mock.side_effect = [(b"private1", b"public1"), (b"private2", b"public2")]
            job_specs = await configurator.get_job_specs(replica_num=0)

        assert len(job_specs) == 2
        assert job_specs[0].ssh_key == JobSSHKey(private="private1", public="public1")
        assert job_specs[1].ssh_key == JobSSHKey(private="private1", public="public1")


@pytest.mark.asyncio
@pytest.mark.usefixtures("image_config_mock")
class TestCommands:
    @pytest.mark.parametrize(
        ["commands", "expected_commands"],
        [
            pytest.param([], ["/entrypoint.sh", "-v"], id="no-commands"),
            pytest.param(["-x", "-u"], ["/entrypoint.sh", "-v", "-x", "-u"], id="with-commands"),
        ],
    )
    async def test_with_entrypoint(self, commands: list[str], expected_commands: list[str]):
        configuration = TaskConfiguration(
            image="debian",
            entrypoint="/entrypoint.sh -v",
            commands=commands,
        )
        run_spec = get_run_spec(run_name="run", repo_id="id", configuration=configuration)
        configurator = TaskJobConfigurator(run_spec)

        job_specs = await configurator.get_job_specs(replica_num=0)

        assert job_specs[0].commands == expected_commands

    @pytest.mark.parametrize(
        ["shell", "expected_shell"],
        [
            pytest.param(None, "/bin/sh", id="default-shell"),
            pytest.param("sh", "/bin/sh", id="sh"),
            pytest.param("bash", "/bin/bash", id="bash"),
            pytest.param("/usr/bin/zsh", "/usr/bin/zsh", id="custom-shell"),
        ],
    )
    async def test_with_commands_and_image(self, shell: Optional[str], expected_shell: str):
        configuration = TaskConfiguration(image="debian", commands=["sleep inf"], shell=shell)
        run_spec = get_run_spec(run_name="run", repo_id="id", configuration=configuration)
        configurator = TaskJobConfigurator(run_spec)

        job_specs = await configurator.get_job_specs(replica_num=0)

        assert job_specs[0].commands == [expected_shell, "-i", "-c", "sleep inf"]

    @pytest.mark.parametrize(
        ["shell", "expected_shell"],
        [
            pytest.param(None, "/bin/bash", id="default-shell"),
            pytest.param("sh", "/bin/sh", id="sh"),
            pytest.param("bash", "/bin/bash", id="bash"),
            pytest.param("/usr/bin/zsh", "/usr/bin/zsh", id="custom-shell"),
        ],
    )
    async def test_with_commands_no_image(self, shell: Optional[str], expected_shell: str):
        configuration = TaskConfiguration(commands=["sleep inf"], shell=shell)
        run_spec = get_run_spec(run_name="run", repo_id="id", configuration=configuration)
        configurator = TaskJobConfigurator(run_spec)

        job_specs = await configurator.get_job_specs(replica_num=0)

        assert job_specs[0].commands == [expected_shell, "-i", "-c", "sleep inf"]

    async def test_no_commands(self, image_config_mock: ImageConfig):
        image_config_mock.entrypoint = ["/entrypoint.sh"]
        image_config_mock.cmd = ["-f", "-x"]
        configuration = TaskConfiguration(image="debian")
        run_spec = get_run_spec(run_name="run", repo_id="id", configuration=configuration)
        configurator = TaskJobConfigurator(run_spec)

        job_specs = await configurator.get_job_specs(replica_num=0)

        assert job_specs[0].commands == ["/entrypoint.sh", "-f", "-x"]
