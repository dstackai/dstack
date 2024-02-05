from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceType,
    LaunchedInstanceInfo,
    Resources,
)
from dstack._internal.core.models.profiles import DEFAULT_POOL_NAME, Profile, ProfileRetryPolicy
from dstack._internal.core.models.runs import InstanceStatus, JobProvisioningData, JobStatus
from dstack._internal.server.background.tasks.process_submitted_jobs import process_submitted_jobs
from dstack._internal.server.models import JobModel
from dstack._internal.server.services.pools import list_project_pool_models
from dstack._internal.server.testing.common import (
    create_instance,
    create_job,
    create_pool,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_run_spec,
)
from dstack.api._public.resources import Resources as MakeResources


class TestProcessSubmittedJobs:
    @pytest.mark.asyncio
    async def test_fails_job_when_no_backends(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
        )
        job = await create_job(
            session=session,
            run=run,
        )
        await process_submitted_jobs()
        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.FAILED

    @pytest.mark.asyncio
    async def test_provisiones_job(self, test_db, session: AsyncSession):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
        )
        job = await create_job(
            session=session,
            run=run,
        )
        offer = InstanceOfferWithAvailability(
            backend=BackendType.AWS,
            instance=InstanceType(
                name="instance",
                resources=Resources(cpus=1, memory_mib=512, spot=False, gpus=[]),
            ),
            region="us",
            price=1.0,
            availability=InstanceAvailability.AVAILABLE,
        )
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock = Mock()
            m.return_value = [backend_mock]
            backend_mock.TYPE = BackendType.AWS
            backend_mock.compute.return_value.get_offers.return_value = [offer]
            backend_mock.compute.return_value.run_job.return_value = LaunchedInstanceInfo(
                instance_id="instance_id",
                region="us",
                ip_address="1.1.1.1",
                username="ubuntu",
                ssh_port=22,
                dockerized=True,
            )
            await process_submitted_jobs()
            m.assert_called_once()
            backend_mock.compute.return_value.get_offers.assert_called_once()
            backend_mock.compute.return_value.run_job.assert_called_once()

        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.PROVISIONING

        await session.refresh(project)
        assert project.default_pool.name == DEFAULT_POOL_NAME

        instance_offer = InstanceOfferWithAvailability.parse_raw(
            project.default_pool.instances[0].offer
        )
        assert offer == instance_offer

        pool_job_provisioning_data = project.default_pool.instances[0].job_provisioning_data
        assert pool_job_provisioning_data == job.job_provisioning_data

    @pytest.mark.asyncio
    async def test_transitions_job_with_retry_to_pending_on_no_capacity(
        self, test_db, session: AsyncSession
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="test-run",
            run_spec=get_run_spec(
                run_name="test-run",
                repo_id=repo.name,
                profile=Profile(
                    name="default",
                    retry_policy=ProfileRetryPolicy(retry=True, limit=3600),
                ),
            ),
        )
        job = await create_job(
            session=session,
            run=run,
            submitted_at=datetime(2023, 1, 2, 3, 0, 0, tzinfo=timezone.utc),
        )
        with patch("dstack._internal.utils.common.get_current_datetime") as datetime_mock:
            datetime_mock.return_value = datetime(2023, 1, 2, 3, 30, 0, tzinfo=timezone.utc)
            await process_submitted_jobs()

        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.PENDING

        await session.refresh(project)
        assert not project.default_pool.instances

    @pytest.mark.asyncio
    async def test_transitions_job_with_outdated_retry_to_failed_on_no_capacity(
        self, test_db, session: AsyncSession
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(
            session=session,
            project_id=project.id,
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="test-run",
            run_spec=get_run_spec(
                run_name="test-run",
                repo_id=repo.name,
                profile=Profile(
                    name="default",
                    retry_policy=ProfileRetryPolicy(retry=True, limit=3600),
                ),
            ),
        )
        job = await create_job(
            session=session,
            run=run,
            submitted_at=datetime(2023, 1, 2, 3, 0, 0, tzinfo=timezone.utc),
        )
        with patch("dstack._internal.utils.common.get_current_datetime") as datetime_mock:
            datetime_mock.return_value = datetime(2023, 1, 2, 5, 0, 0, tzinfo=timezone.utc)
            await process_submitted_jobs()

        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.FAILED

        await session.refresh(project)
        assert not project.default_pool.instances

    @pytest.mark.asyncio
    async def test_job_with_instance(self, test_db, session: AsyncSession):
        project = await create_project(session)
        user = await create_user(session)
        repo = await create_repo(
            session,
            project_id=project.id,
        )
        pools = await list_project_pool_models(session, project)
        pool = None
        for pool_item in pools:
            if pool_item == DEFAULT_POOL_NAME:
                pool = pool_item
        if pool is None:
            pool = await create_pool(session, project)
        resources = MakeResources(cpu=2, memory="12GB")
        await create_instance(session, project, pool, InstanceStatus.READY, resources)
        await session.refresh(pool)
        run = await create_run(
            session,
            project=project,
            repo=repo,
            user=user,
        )
        job_provisioning_data = JobProvisioningData(
            backend=BackendType.LOCAL,
            instance_type=InstanceType(
                name="local",
                resources=Resources(cpus=2, memory_mib=12 * 1024, gpus=[], spot=False),
            ),
            instance_id="0000-0000",
            hostname="localhost",
            region="",
            price=0.0,
            username="root",
            ssh_port=22,
            dockerized=False,
            pool_id=str(pool.id),
            backend_data=None,
            ssh_proxy=None,
        )
        with patch(
            "dstack._internal.server.services.jobs.configurators.base.get_default_python_verison"
        ) as PyVersion:
            PyVersion.return_value = "3.10"
            job = await create_job(
                session,
                run=run,
                job_provisioning_data=job_provisioning_data,
            )
        await process_submitted_jobs()
        await session.refresh(job)
        assert job is not None
        assert job.status == JobStatus.PROVISIONING

        res = await session.execute(select(JobModel).where())
        jm = res.all()[0][0]
        assert jm.job_num == 0
        assert jm.run_name == "test-run"
        assert jm.job_name == "test-run-0"
        assert jm.submission_num == 0
        assert jm.status == JobStatus.PROVISIONING
        assert jm.error_code is None
        assert (
            jm.job_spec_data
            == r"""{"job_num": 0, "job_name": "test-run-0", "app_specs": [], "commands": ["/bin/bash", "-i", "-c", "(echo pip install ipykernel... && pip install -q --no-cache-dir ipykernel 2> /dev/null) || echo \"no pip, ipykernel was not installed\" && echo '' && echo To open in VS Code Desktop, use link below: && echo '' && echo '  vscode://vscode-remote/ssh-remote+test-run/workflow' && echo '' && echo 'To connect via SSH, use: `ssh test-run`' && echo '' && echo -n 'To exit, press Ctrl+C.' && tail -f /dev/null"], "env": {}, "gateway": null, "home_dir": "/root", "image_name": "dstackai/base:py3.10-0.4rc4-cuda-12.1", "max_duration": 21600, "registry_auth": null, "requirements": {"resources": {"cpu": {"min": 2, "max": null}, "memory": {"min": 8.0, "max": null}, "shm_size": null, "gpu": null, "disk": null}, "max_price": null, "spot": false}, "retry_policy": {"retry": false, "limit": null}, "working_dir": ".", "pool_name": null}"""
        )
        assert jm.job_provisioning_data == (
            '{"backend": "datacrunch", "instance_type": {"name": "instance", "resources": '
            '{"cpus": 1, "memory_mib": 512, "gpus": [], "spot": false, "disk": '
            '{"size_mib": 102400}, "description": ""}}, "instance_id": '
            '"running_instance.id", "pool_id": "1b2b4c57-5851-487f-b92e-948f946dfa49", '
            '"hostname": "running_instance.ip", "region": "running_instance.location", '
            '"price": 0.1, "username": "root", "ssh_port": 22, "dockerized": true, '
            '"backend_data": null}'
        )
