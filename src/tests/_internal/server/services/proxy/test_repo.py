from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.instances import SSHConnectionParams
from dstack._internal.core.models.runs import JobStatus
from dstack._internal.proxy.lib.models import Project
from dstack._internal.server.services.proxy.repo import ServerProxyRepo
from dstack._internal.server.testing.common import (
    create_instance,
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_job_provisioning_data,
    get_remote_connection_info,
    get_run_spec,
    get_ssh_key,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestServerProxyRepo:
    async def test_service_project_needs_no_additional_query(
        self, test_db, session: AsyncSession
    ) -> None:
        user = await create_user(session)
        project = await create_project(session, owner=user, ssh_private_key="project key")
        source_repo = await create_repo(session, project_id=project.id)
        run = await create_run(
            session,
            project=project,
            repo=source_repo,
            user=user,
            run_spec=get_run_spec(
                repo_id=source_repo.name,
                configuration=ServiceConfiguration(commands=["python serve.py"], port=8000),
            ),
        )
        jump_key = get_ssh_key()
        instance = await create_instance(
            session,
            project=project,
            remote_connection_info=get_remote_connection_info(
                ssh_proxy=SSHConnectionParams(hostname="jump", username="ubuntu", port=22),
                ssh_proxy_keys=[jump_key],
            ),
        )
        await create_job(
            session,
            run=run,
            instance=instance,
            status=JobStatus.RUNNING,
            ready=True,
            registered=True,
            job_provisioning_data=get_job_provisioning_data(),
        )

        repo = ServerProxyRepo(session)
        with patch.object(session, "execute", wraps=session.execute) as execute:
            service = await repo.get_service(project.name, run.run_name)
            assert service is not None
            assert service.replicas[0].ssh_head_proxy_private_key == jump_key.private
            assert await repo.get_project(project.name) == Project(
                name=project.name, ssh_private_key="project key"
            )
            # Reuse the project loaded by the service query; release its connection
            # before the caller opens or updates an SSH tunnel.
            assert execute.await_count == 1
            assert not session.in_transaction()

    async def test_get_project_without_loading_service(
        self, test_db, session: AsyncSession
    ) -> None:
        project = await create_project(session, ssh_private_key="project key")
        repo = ServerProxyRepo(session)
        assert await repo.get_project(project.name) == Project(
            name=project.name, ssh_private_key="project key"
        )
        assert not session.in_transaction()
