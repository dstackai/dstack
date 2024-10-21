from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.models.common import is_core_model_instance
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.instances import SSHConnectionParams
from dstack._internal.core.models.runs import JobProvisioningData, JobStatus, RunSpec
from dstack._internal.proxy.repos.base import BaseProxyRepo, Project, Replica, Service
from dstack._internal.server.models import JobModel, ProjectModel, RunModel


class DBProxyRepo(BaseProxyRepo):
    """
    A repo implementation used by dstack-proxy running within dstack-server.
    Retrieves data from dstack-server's database. Since the database is
    populated by dstack-server, all or most writer methods in this
    implementation are expected to be empty.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_service(self, project_name: str, run_name: str) -> Optional[Service]:
        res = await self.session.execute(
            select(JobModel)
            .join(JobModel.project)
            .join(JobModel.run)
            .where(
                ProjectModel.name == project_name,
                RunModel.gateway_id.is_(None),
                JobModel.run_name == run_name,
                JobModel.status == JobStatus.RUNNING,
                JobModel.job_num == 0,
            )
            .options(joinedload(JobModel.run))
        )
        jobs = res.scalars().all()
        if not len(jobs):
            return None
        run = jobs[0].run
        run_spec = RunSpec.__response__.parse_raw(run.run_spec)
        if not is_core_model_instance(run_spec.configuration, ServiceConfiguration):
            return None
        replicas = []
        for job in jobs:
            jpd: JobProvisioningData = JobProvisioningData.__response__.parse_raw(
                job.job_provisioning_data
            )
            if not jpd.dockerized:
                ssh_destination = f"{jpd.username}@{jpd.hostname}"
                ssh_port = jpd.ssh_port
                ssh_proxy = jpd.ssh_proxy
            else:
                ssh_destination = "root@localhost"  # TODO(#1535): support non-root images properly
                ssh_port = 10022
                ssh_proxy = SSHConnectionParams(
                    hostname=jpd.hostname,
                    username=jpd.username,
                    port=jpd.ssh_port,
                )
            replica = Replica(
                id=job.id.hex,
                ssh_destination=ssh_destination,
                ssh_port=ssh_port,
                ssh_proxy=ssh_proxy,
            )
            replicas.append(replica)
        return Service(
            id=run.id.hex,
            run_name=run.run_name,
            auth=run_spec.configuration.auth,
            app_port=run_spec.configuration.port.container_port,
            replicas=replicas,
        )

    async def add_service(self, project_name: str, service: Service) -> None:
        pass

    async def get_project(self, name: str) -> Optional[Project]:
        res = await self.session.execute(select(ProjectModel).where(ProjectModel.name == name))
        project = res.scalar_one_or_none()
        if project is None:
            return None
        return Project(
            name=project.name,
            ssh_private_key=project.ssh_private_key,
        )

    async def add_project(self, project: Project) -> None:
        pass
