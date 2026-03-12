from typing import Optional

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.consts import DSTACK_RUNNER_SSH_PORT
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import NetworkMode
from dstack._internal.core.models.instances import SSHConnectionParams, SSHKey
from dstack._internal.core.models.runs import (
    JobRuntimeData,
)
from dstack._internal.server.models import ProjectModel, RunModel
from dstack._internal.server.services.ssh import get_container_ssh_credentials
from dstack._internal.server.testing.common import (
    create_instance,
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_job_provisioning_data,
    get_job_runtime_data,
    get_remote_connection_info,
)
from dstack._internal.utils.path import FileContent


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
@pytest.mark.usefixtures("test_db", "image_config_mock")
class TestGetContainerSSHCredentials:
    instance_project_key = "instance-project-key"
    run_project_key = "run-project-key"

    @pytest_asyncio.fixture
    async def instance_project(self, session: AsyncSession) -> ProjectModel:
        owner = await create_user(session=session, name="instance-project-owner")
        return await create_project(
            session=session,
            name="instance-project",
            owner=owner,
            ssh_private_key=self.instance_project_key,
        )

    @pytest_asyncio.fixture
    async def run(self, session: AsyncSession) -> RunModel:
        run_project_owner = await create_user(session=session, name="run-project-owner")
        run_project = await create_project(
            session=session, name="run-project", ssh_private_key=self.run_project_key
        )
        repo = await create_repo(session=session, project_id=run_project.id)
        run = await create_run(
            session=session, project=run_project, user=run_project_owner, repo=repo
        )
        # Triggers session magic, attaches ProjectModel to JobModel somehow
        assert run.project is not None
        return run

    @pytest.mark.parametrize(
        ["jrd", "expected_port"],
        [
            pytest.param(None, DSTACK_RUNNER_SSH_PORT, id="no-jrd"),
            pytest.param(
                get_job_runtime_data(network_mode=NetworkMode.HOST, ports={}),
                DSTACK_RUNNER_SSH_PORT,
                id="host",
            ),
            pytest.param(
                get_job_runtime_data(
                    network_mode=NetworkMode.HOST, ports={DSTACK_RUNNER_SSH_PORT: 32772}
                ),
                32772,
                id="bridge",
            ),
        ],
    )
    async def test_vm_based_backend(
        self,
        session: AsyncSession,
        instance_project: ProjectModel,
        run: RunModel,
        jrd: Optional[JobRuntimeData],
        expected_port: int,
    ):
        instance = await create_instance(
            session=session, project=instance_project, backend=BackendType.AWS
        )
        jpd = get_job_provisioning_data(
            backend=BackendType.AWS,
            dockerized=True,
            hostname="80.80.80.80",
            username="ubuntu",
            ssh_port=22,
            ssh_proxy=None,
        )
        job = await create_job(
            session=session,
            run=run,
            instance=instance,
            job_provisioning_data=jpd,
            job_runtime_data=jrd,
        )

        hosts = get_container_ssh_credentials(job)

        assert hosts == [
            (
                SSHConnectionParams(
                    hostname="80.80.80.80",
                    username="ubuntu",
                    port=22,
                ),
                FileContent(self.instance_project_key),
            ),
            (
                SSHConnectionParams(
                    hostname="localhost",
                    username="root",
                    port=expected_port,
                ),
                FileContent(self.run_project_key),
            ),
        ]

    async def test_container_based_backend(
        self,
        session: AsyncSession,
        instance_project: ProjectModel,
        run: RunModel,
    ):
        instance = await create_instance(
            session=session, project=instance_project, backend=BackendType.RUNPOD
        )
        jpd = get_job_provisioning_data(
            backend=BackendType.RUNPOD,
            dockerized=False,
            hostname="100.100.100.100",
            username="root",
            ssh_port=32768,
            ssh_proxy=None,
        )
        job = await create_job(
            session=session,
            run=run,
            instance=instance,
            job_provisioning_data=jpd,
        )

        hosts = get_container_ssh_credentials(job)

        assert hosts == [
            (
                SSHConnectionParams(
                    hostname="100.100.100.100",
                    username="root",
                    port=32768,
                ),
                FileContent(self.run_project_key),
            ),
        ]

    async def test_container_based_backend_with_proxy(
        self,
        session: AsyncSession,
        instance_project: ProjectModel,
        run: RunModel,
    ):
        instance = await create_instance(
            session=session, project=instance_project, backend=BackendType.KUBERNETES
        )
        jpd = get_job_provisioning_data(
            backend=BackendType.KUBERNETES,
            dockerized=False,
            hostname="10.105.30.22",
            username="root",
            ssh_port=DSTACK_RUNNER_SSH_PORT,
            ssh_proxy=SSHConnectionParams(
                hostname="120.120.120.120",
                username="root",
                port=30022,
            ),
        )
        job = await create_job(
            session=session,
            run=run,
            instance=instance,
            job_provisioning_data=jpd,
        )

        hosts = get_container_ssh_credentials(job)

        assert hosts == [
            (
                SSHConnectionParams(
                    hostname="120.120.120.120",
                    username="root",
                    port=30022,
                ),
                FileContent(self.run_project_key),
            ),
            (
                SSHConnectionParams(
                    hostname="10.105.30.22",
                    username="root",
                    port=DSTACK_RUNNER_SSH_PORT,
                ),
                FileContent(self.run_project_key),
            ),
        ]

    async def test_ssh_instance_with_head_proxy(
        self,
        session: AsyncSession,
        instance_project: ProjectModel,
        run: RunModel,
    ):
        rci = get_remote_connection_info(
            host="192.168.100.50",
            port=22222,
            ssh_user="ubuntu",
            # User-provided key is only used for instance provisioning, then we always use
            # the project key, which is added during provisioning
            ssh_keys=[SSHKey(public="public", private="instance-key")],
            ssh_proxy=SSHConnectionParams(
                hostname="140.140.140.140",
                username="bastion",
                port=22,
            ),
            ssh_proxy_keys=[SSHKey(public="public", private="head-key")],
        )
        instance = await create_instance(
            session=session,
            project=instance_project,
            backend=BackendType.REMOTE,
            remote_connection_info=rci,
        )
        jpd = get_job_provisioning_data(
            backend=BackendType.REMOTE,
            dockerized=True,
            hostname="192.168.100.50",
            username="ubuntu",
            ssh_port=22222,
            # Actually, JobModel.job_provisioning_data.ssh_proxy is set to
            # InstanceModel.remote_connection_info.ssh_proxy but not used in the function we test
            ssh_proxy=None,
        )
        job = await create_job(
            session=session,
            run=run,
            instance=instance,
            job_provisioning_data=jpd,
            # jrd is tested in vm-based backend tests
            job_runtime_data=None,
        )

        hosts = get_container_ssh_credentials(job)

        assert hosts == [
            (
                SSHConnectionParams(
                    hostname="140.140.140.140",
                    username="bastion",
                    port=22,
                ),
                FileContent("head-key"),
            ),
            (
                SSHConnectionParams(
                    hostname="192.168.100.50",
                    username="ubuntu",
                    port=22222,
                ),
                FileContent(self.instance_project_key),
            ),
            (
                SSHConnectionParams(
                    hostname="localhost",
                    username="root",
                    port=DSTACK_RUNNER_SSH_PORT,
                ),
                FileContent(self.run_project_key),
            ),
        ]

    async def test_local_backend(
        self,
        session: AsyncSession,
        instance_project: ProjectModel,
        run: RunModel,
    ):
        instance = await create_instance(
            session=session, project=instance_project, backend=BackendType.LOCAL
        )
        jpd = get_job_provisioning_data(
            backend=BackendType.LOCAL,
            dockerized=True,
            hostname="127.0.0.1",
            username="root",
            ssh_port=DSTACK_RUNNER_SSH_PORT,
            ssh_proxy=None,
        )
        job = await create_job(
            session=session,
            run=run,
            instance=instance,
            job_provisioning_data=jpd,
            # jrd is tested in vm-based backend tests
            job_runtime_data=None,
        )

        hosts = get_container_ssh_credentials(job)

        assert hosts == [
            (
                SSHConnectionParams(
                    hostname="localhost",
                    username="root",
                    port=DSTACK_RUNNER_SSH_PORT,
                ),
                FileContent(self.run_project_key),
            ),
        ]
