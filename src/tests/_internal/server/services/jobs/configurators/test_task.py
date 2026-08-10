from typing import Optional
from unittest.mock import patch

import pytest

from dstack._internal.core.models.configurations import NodeGroup, TaskConfiguration
from dstack._internal.core.models.resources import GPUSpec, ResourcesSpec
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
class TestNodeGroups:
    async def test_assigns_contiguous_ranks_and_metadata(self):
        configuration = TaskConfiguration(
            image="debian",
            groups=[
                NodeGroup(name="head", nodes=2, commands=["echo head"]),
                NodeGroup(name="workers", nodes=2, commands=["echo worker"]),
            ],
        )
        run_spec = get_run_spec(run_name="run", repo_id="id", configuration=configuration)
        configurator = TaskJobConfigurator(run_spec)

        job_specs = await configurator.get_job_specs(replica_num=0)

        assert len(job_specs) == 4
        assert [j.job_num for j in job_specs] == [0, 1, 2, 3]
        assert [j.jobs_per_replica for j in job_specs] == [4, 4, 4, 4]
        assert [j.node_group_name for j in job_specs] == [
            "head",
            "head",
            "workers",
            "workers",
        ]
        assert [j.node_group_index for j in job_specs] == [0, 0, 1, 1]
        assert [j.node_group_job_index for j in job_specs] == [0, 1, 0, 1]

    async def test_uses_per_group_commands_and_resources(self):
        configuration = TaskConfiguration(
            image="debian",
            groups=[
                NodeGroup(
                    name="head",
                    nodes=1,
                    commands=["echo head"],
                    resources=ResourcesSpec(gpu=GPUSpec(name=["H100"], count=1)),
                ),
                NodeGroup(
                    name="workers",
                    nodes=1,
                    commands=["echo worker"],
                    resources=ResourcesSpec(gpu=GPUSpec(name=["A100"], count=2)),
                ),
            ],
        )
        run_spec = get_run_spec(run_name="run", repo_id="id", configuration=configuration)
        configurator = TaskJobConfigurator(run_spec)

        job_specs = await configurator.get_job_specs(replica_num=0)

        assert "echo head" in job_specs[0].commands[-1]
        assert "echo worker" in job_specs[1].commands[-1]
        assert job_specs[0].requirements.resources.gpu.name == ["H100"]
        assert job_specs[0].requirements.resources.gpu.count.min == 1
        assert job_specs[1].requirements.resources.gpu.name == ["A100"]
        assert job_specs[1].requirements.resources.gpu.count.min == 2

    async def test_group_without_resources_does_not_inherit_top_level(self):
        """Same as replica groups: omitted group resources → ResourcesSpec(), not top-level."""
        configuration = TaskConfiguration(
            image="debian",
            resources=ResourcesSpec(gpu=GPUSpec(name=["H100"], count=1)),
            groups=[
                NodeGroup(name="head", nodes=1, commands=["echo head"]),
            ],
        )
        run_spec = get_run_spec(run_name="run", repo_id="id", configuration=configuration)
        configurator = TaskJobConfigurator(run_spec)

        job_specs = await configurator.get_job_specs(replica_num=0)

        assert job_specs[0].requirements.resources.gpu.name is None


@pytest.mark.asyncio
@pytest.mark.usefixtures("image_config_mock")
class TestServerAccess:
    async def test_adds_transport_without_credentials(self):
        configuration = TaskConfiguration(image="debian", commands=["true"], dstack=True)
        run_spec = get_run_spec(run_name="run", repo_id="id", configuration=configuration)
        configurator = TaskJobConfigurator(run_spec)

        job_spec = (await configurator.get_job_specs(replica_num=0))[0]

        assert "dstack" not in job_spec.model_dump()
        assert job_spec.env == {
            "DSTACK_SERVER_URL": "http+unix://%2Frun%2Fdstack%2Fserver.sock",
        }

    async def test_disabled_by_default(self):
        configuration = TaskConfiguration(image="debian", commands=["true"])
        run_spec = get_run_spec(run_name="run", repo_id="id", configuration=configuration)
        configurator = TaskJobConfigurator(run_spec)

        job_spec = (await configurator.get_job_specs(replica_num=0))[0]

        assert "DSTACK_SERVER_URL" not in job_spec.env

    async def test_preserves_explicit_transport_env(self):
        configuration = TaskConfiguration(
            image="debian",
            commands=["true"],
            dstack=True,
            env={
                "DSTACK_SERVER_URL": "https://server.example.com",
            },
        )
        run_spec = get_run_spec(run_name="run", repo_id="id", configuration=configuration)
        configurator = TaskJobConfigurator(run_spec)

        job_spec = (await configurator.get_job_specs(replica_num=0))[0]

        assert job_spec.env["DSTACK_SERVER_URL"] == "https://server.example.com"


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
        configuration = TaskConfiguration(python="3.12", commands=["sleep inf"], shell=shell)
        run_spec = get_run_spec(run_name="run", repo_id="id", configuration=configuration)
        configurator = TaskJobConfigurator(run_spec)

        job_specs = await configurator.get_job_specs(replica_num=0)

        assert job_specs[0].commands == [
            expected_shell,
            "-i",
            "-c",
            (
                "eval $(echo 'export DSTACK_VENV_DIR=/dstack/venv' | sudo tee -a /dstack/profile)"
                " && sudo rm -rf $DSTACK_VENV_DIR"
                " && sudo mkdir $DSTACK_VENV_DIR"
                " && sudo chown $(id -u):$(id -g) $DSTACK_VENV_DIR"
                " && uv venv -q --prompt dstack -p 3.12 --seed $DSTACK_VENV_DIR"
                " && eval $(echo '. $DSTACK_VENV_DIR/bin/activate' | sudo tee -a /dstack/profile)"
                " && sleep inf"
            ),
        ]

    async def test_no_commands(self, image_config_mock: ImageConfig):
        image_config_mock.entrypoint = ["/entrypoint.sh"]
        image_config_mock.cmd = ["-f", "-x"]
        configuration = TaskConfiguration(image="debian")
        run_spec = get_run_spec(run_name="run", repo_id="id", configuration=configuration)
        configurator = TaskJobConfigurator(run_spec)

        job_specs = await configurator.get_job_specs(replica_num=0)

        assert job_specs[0].commands == ["/entrypoint.sh", "-f", "-x"]
