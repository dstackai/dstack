from unittest.mock import patch

import pytest

from dstack._internal.core.models.configurations import TaskConfiguration
from dstack._internal.core.models.runs import JobSSHKey
from dstack._internal.server.services.jobs.configurators.task import TaskJobConfigurator
from dstack._internal.server.testing.common import get_run_spec


@pytest.mark.asyncio
@pytest.mark.usefixtures("image_config_mock")
class TestTaskJobConfigurator:
    async def test_ssh_key_single_node(self):
        configuration = TaskConfiguration(nodes=1, image="debian")
        run_spec = get_run_spec(run_name="run", repo_id="id", configuration=configuration)
        configurator = TaskJobConfigurator(run_spec)

        job_specs = await configurator.get_job_specs(replica_num=0)

        assert len(job_specs) == 1
        assert job_specs[0].ssh_key is None

    async def test_ssh_key_multi_node(self):
        configuration = TaskConfiguration(nodes=2, image="debian")
        run_spec = get_run_spec(run_name="run", repo_id="id", configuration=configuration)
        configurator = TaskJobConfigurator(run_spec)

        with patch("dstack._internal.utils.crypto.generate_rsa_key_pair_bytes") as gen_mock:
            gen_mock.side_effect = [(b"private1", b"public1"), (b"private2", b"public2")]
            job_specs = await configurator.get_job_specs(replica_num=0)

        assert len(job_specs) == 2
        assert job_specs[0].ssh_key == JobSSHKey(private="private1", public="public1")
        assert job_specs[1].ssh_key == JobSSHKey(private="private1", public="public1")
