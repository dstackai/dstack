import asyncio
import json
import shlex
import subprocess
import tempfile
from datetime import timezone
from typing import List, Optional, Sequence

import pkg_resources
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.utils.random_names as random_names
from dstack._internal.core.errors import ConfigurationError, DstackError, NotFoundError, SSHError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.gateways import Gateway
from dstack._internal.core.models.runs import Job
from dstack._internal.server.models import GatewayModel, ProjectModel
from dstack._internal.server.services.backends import (
    get_project_backend_by_type,
    get_project_backends_with_models,
)
from dstack._internal.server.utils.common import run_async
from dstack._internal.utils.crypto import generate_rsa_key_pair_bytes
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def list_project_gateways(session: AsyncSession, project: ProjectModel) -> List[Gateway]:
    gateways = await list_project_gateway_models(session=session, project=project)
    return [gateway_model_to_gateway(g) for g in gateways]


async def get_gateway_by_name(
    session: AsyncSession, project: ProjectModel, name: str
) -> Optional[Gateway]:
    gateway = await get_project_gateway_model_by_name(session=session, project=project, name=name)
    if gateway is None:
        return None
    return gateway_model_to_gateway(gateway)


async def get_project_default_gateway(
    session: AsyncSession, project: ProjectModel
) -> Optional[Gateway]:
    gateway: Optional[GatewayModel] = project.default_gateway
    if gateway is None:
        return None
    return gateway_model_to_gateway(gateway)


async def create_gateway(
    session: AsyncSession,
    project: ProjectModel,
    name: Optional[str],
    backend_type: BackendType,
    region: str,
) -> Gateway:
    for backend_model, backend in await get_project_backends_with_models(project):
        if backend_model.type == backend_type:
            break
    else:
        raise NotFoundError()

    if name is None:
        name = await generate_gateway_name(session=session, project=project)

    gateway = GatewayModel(  # reserve name
        name=name,
        ip_address="",  # to be filled after provisioning
        instance_id="",  # to be filled after provisioning
        region=region,
        project_id=project.id,
        backend_id=backend_model.id,
    )
    session.add(gateway)
    await session.commit()

    if project.default_gateway is None:
        await set_default_gateway(session=session, project=project, name=name)

    try:
        info = await run_async(
            backend.compute().create_gateway,
            name,
            project.ssh_public_key,
            region,
            project.name,
        )
        await session.execute(
            update(GatewayModel)
            .where(
                GatewayModel.project_id == project.id,
                GatewayModel.name == name,
            )
            .values(
                ip_address=info.ip_address,
                region=info.region,
                instance_id=info.instance_id,
            )
        )
        await session.commit()
        await session.refresh(gateway)
    except Exception:  # rollback, release reserved name
        await session.execute(
            delete(GatewayModel).where(
                GatewayModel.project_id == project.id,
                GatewayModel.name == name,
            )
        )
        await session.commit()
        raise

    return gateway_model_to_gateway(gateway)


async def delete_gateways(session: AsyncSession, project: ProjectModel, gateways_names: List[str]):
    tasks = []
    gateways = []
    for gateway in await list_project_gateway_models(session=session, project=project):
        if gateway.name not in gateways_names:
            continue
        backend = await get_project_backend_by_type(project, gateway.backend.type)
        tasks.append(
            run_async(backend.compute().terminate_instance, gateway.instance_id, gateway.region)
        )
        gateways.append(gateway)
    # terminate in parallel
    terminate_results = await asyncio.gather(*tasks, return_exceptions=True)
    for gateway, error in zip(gateways, terminate_results):
        if isinstance(error, Exception):
            continue  # ignore error, but keep gateway
        await session.delete(gateway)
    await session.commit()


async def set_gateway_wildcard_domain(
    session: AsyncSession, project: ProjectModel, name: str, wildcard_domain: Optional[str]
) -> Gateway:
    await session.execute(
        update(GatewayModel)
        .where(
            GatewayModel.project_id == project.id,
            GatewayModel.name == name,
        )
        .values(
            wildcard_domain=wildcard_domain,
        )
    )
    await session.commit()
    res = await session.execute(
        select(GatewayModel).where(
            GatewayModel.project_id == project.id, GatewayModel.name == name
        )
    )
    gateway = res.scalar()
    if gateway is None:
        raise NotFoundError()
    return gateway_model_to_gateway(gateway)


async def set_default_gateway(session: AsyncSession, project: ProjectModel, name: str):
    gateway = await get_project_gateway_model_by_name(session=session, project=project, name=name)
    if gateway is None:
        raise NotFoundError()
    await session.execute(
        update(ProjectModel)
        .where(
            ProjectModel.id == project.id,
        )
        .values(
            default_gateway_id=gateway.id,
        )
    )
    await session.commit()


async def list_project_gateway_models(
    session: AsyncSession, project: ProjectModel
) -> Sequence[GatewayModel]:
    res = await session.execute(select(GatewayModel).where(GatewayModel.project_id == project.id))
    return res.scalars().all()


async def get_project_gateway_model_by_name(
    session: AsyncSession, project: ProjectModel, name: str
) -> Optional[GatewayModel]:
    res = await session.execute(
        select(GatewayModel).where(
            GatewayModel.project_id == project.id, GatewayModel.name == name
        )
    )
    return res.scalar()


async def generate_gateway_name(session: AsyncSession, project: ProjectModel) -> str:
    gateways = await list_project_gateway_models(session=session, project=project)
    names = {g.name for g in gateways}
    while True:
        name = random_names.generate_name()
        if name not in names:
            return name


async def register_service_jobs(session: AsyncSession, project: ProjectModel, jobs: List[Job]):
    # we are expecting that all jobs are for the same service and the same gateway
    gateway_name = jobs[0].job_spec.gateway.gateway_name
    if gateway_name is None:
        gateway = await get_project_default_gateway(session=session, project=project)
        if gateway is None:
            raise DstackError("Default gateway is not set")
    else:
        gateway = await get_gateway_by_name(session=session, project=project, name=gateway_name)
        if gateway is None:
            raise NotFoundError("Gateway does not exist")

    domain = gateway.wildcard_domain.lstrip("*.") if gateway.wildcard_domain else None
    private_bytes, public_bytes = generate_rsa_key_pair_bytes(
        comment=f"{project}/{jobs[0].job_spec.job_name}"
    )
    for i, job in enumerate(jobs):
        job.job_spec.gateway.gateway_name = gateway.name
        job.job_spec.gateway.ssh_key = private_bytes.decode()
        if domain is not None:
            job.job_spec.gateway.secure = True
            job.job_spec.gateway.public_port = 443
            job.job_spec.gateway.hostname = f"{job.job_spec.job_name}.{domain}"
        else:
            job.job_spec.gateway.secure = False
            # use provided public port
            job.job_spec.gateway.hostname = gateway.ip_address
    await run_async(
        configure_gateway_over_ssh,
        f"ubuntu@{gateway.ip_address}",
        project.ssh_private_key,
        public_bytes.decode(),
        jobs,
    )


def gateway_model_to_gateway(gateway_model: GatewayModel) -> Gateway:
    return Gateway(
        name=gateway_model.name,
        ip_address=gateway_model.ip_address,
        instance_id=gateway_model.instance_id,
        region=gateway_model.region,
        wildcard_domain=gateway_model.wildcard_domain,
        default=gateway_model.project.default_gateway_id == gateway_model.id,
        created_at=gateway_model.created_at.replace(tzinfo=timezone.utc),
        backend=gateway_model.backend.type,
    )


def configure_gateway_over_ssh(host: str, id_rsa: str, authorized_key: str, jobs: List[Job]):
    id_rsa_file = tempfile.NamedTemporaryFile("w")
    id_rsa_file.write(id_rsa)
    id_rsa_file.flush()

    payload = {
        "authorized_key": authorized_key,
        "services": [
            {
                "hostname": job.job_spec.gateway.hostname,
                "port": job.job_spec.gateway.public_port,
                "secure": job.job_spec.gateway.secure,
            }
            for job in jobs
        ],
    }

    logger.debug("Configuring %s gateway over SSH: %s", host, payload["services"])
    script_path = pkg_resources.resource_filename(
        "dstack._internal.server", "scripts/configure_gateway.py"
    )
    with open(script_path, "r") as script:
        cmd = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-i",
            id_rsa_file.name,
            host,
            f"sudo python3 - {shlex.quote(json.dumps(payload))}",
        ]
        proc = subprocess.Popen(cmd, stdin=script, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        if b"Certbot failed:" in stderr:
            # TODO pass error to the client
            raise ConfigurationError("Certbot failed, check wildcard domain correctness")
        raise SSHError(stderr.decode())

    sockets = json.loads(stdout)
    for job, socket in zip(jobs, sockets):
        job.job_spec.gateway.sock_path = socket
