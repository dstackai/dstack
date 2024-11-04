from typing import List, Optional

import pydantic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.models.common import is_core_model_instance
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.gateways import AnyModel
from dstack._internal.core.models.instances import SSHConnectionParams
from dstack._internal.core.models.runs import (
    JobProvisioningData,
    JobStatus,
    RunSpec,
    RunStatus,
    ServiceSpec,
)
from dstack._internal.proxy.repos.base import (
    AnyModelFormat,
    BaseProxyRepo,
    ChatModel,
    OpenAIChatModelFormat,
    Project,
    Replica,
    Service,
    TGIChatModelFormat,
)
from dstack._internal.server.models import JobModel, ProjectModel, RunModel
from dstack._internal.server.security.permissions import is_project_member


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

    async def list_models(self, project_name: str) -> List[ChatModel]:
        res = await self.session.execute(
            select(RunModel)
            .join(RunModel.project)
            .where(
                ProjectModel.name == project_name,
                RunModel.gateway_id.is_(None),
                RunModel.service_spec.is_not(None),
                RunModel.status == RunStatus.RUNNING,
            )
        )
        models = []
        for run in res.scalars().all():
            service_spec: ServiceSpec = ServiceSpec.__response__.parse_raw(run.service_spec)
            model_spec = service_spec.model
            model_options_obj = service_spec.options.get("openai", {}).get("model")
            if model_spec is None or model_options_obj is None:
                continue
            model_options = pydantic.parse_obj_as(AnyModel, model_options_obj)
            model = ChatModel(
                name=model_spec.name,
                created_at=run.submitted_at,
                run_name=run.run_name,
                format_spec=_model_options_to_format_spec(model_options),
            )
            models.append(model)
        return models

    async def get_model(self, project_name: str, name: str) -> Optional[ChatModel]:
        models = await self.list_models(project_name)
        models = [m for m in models if m.name == name]
        if not models:
            return None
        # If there are many models with the same name, choose the most recent
        return max(models, key=lambda m: m.created_at)

    async def add_model(self, project_name: str, model: ChatModel) -> None:
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

    async def is_project_member(self, project_name: str, token: str) -> bool:
        return await is_project_member(self.session, project_name, token)


def _model_options_to_format_spec(model: AnyModel) -> AnyModelFormat:
    if model.type == "chat":
        if model.format == "openai":
            return OpenAIChatModelFormat(
                format="openai",
                prefix=model.prefix,
            )
        elif model.format == "tgi":
            return TGIChatModelFormat(
                format="tgi",
                chat_template=model.chat_template,
                eos_token=model.eos_token,
            )
        else:
            raise RuntimeError(f"Unexpected model format {model.format}")
    else:
        raise RuntimeError(f"Unexpected model type {model.type}")
