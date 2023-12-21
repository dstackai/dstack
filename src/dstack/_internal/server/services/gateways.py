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
from dstack._internal.core.errors import GatewayError, ResourceNotExistsError, ServerClientError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.gateways import Gateway
from dstack._internal.core.models.runs import Job
from dstack._internal.server.models import GatewayComputeModel, GatewayModel, ProjectModel
from dstack._internal.server.services.backends import (
    get_project_backend_by_type_or_error,
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
        raise ResourceNotExistsError()

    if name is None:
        name = await generate_gateway_name(session=session, project=project)

    gateway = GatewayModel(  # reserve name
        name=name,
        region=region,
        project_id=project.id,
        backend_id=backend_model.id,
    )
    session.add(gateway)
    await session.commit()

    if project.default_gateway is None:
        await set_default_gateway(session=session, project=project, name=name)

    private_bytes, public_bytes = generate_rsa_key_pair_bytes()
    gateway_ssh_private_key = private_bytes.decode()
    gateway_ssh_public_key = public_bytes.decode()

    try:
        info = await run_async(
            backend.compute().create_gateway,
            name,
            gateway_ssh_public_key,
            region,
            project.name,
        )
        gateway_compute = GatewayComputeModel(
            backend_id=backend_model.id,
            ip_address=info.ip_address,
            region=info.region,
            instance_id=info.instance_id,
            ssh_private_key=gateway_ssh_private_key,
            ssh_public_key=gateway_ssh_private_key,
        )
        session.add(gateway_compute)
        await session.commit()
        await session.refresh(gateway_compute)
        await session.execute(
            update(GatewayModel)
            .where(
                GatewayModel.project_id == project.id,
                GatewayModel.name == name,
            )
            .values(gateway_compute_id=gateway_compute.id)
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
        if gateway.backend.type == BackendType.DSTACK:
            continue
        if gateway.name not in gateways_names:
            continue
        backend = await get_project_backend_by_type_or_error(project, gateway.backend.type)
        if gateway.gateway_compute is not None:
            tasks.append(
                run_async(
                    backend.compute().terminate_instance,
                    gateway.gateway_compute.instance_id,
                    gateway.region,
                    None,
                )
            )
        else:
            tasks.append(run_async(lambda: ...))
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
    gateway = await get_project_gateway_model_by_name(
        session=session,
        project=project,
        name=name,
    )
    if gateway is None:
        raise ResourceNotExistsError()
    if gateway.backend.type == BackendType.DSTACK:
        raise ServerClientError("Custom domains for dstack Cloud gateway are not supported")
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
    gateway = await get_project_gateway_model_by_name(
        session=session,
        project=project,
        name=name,
    )
    if gateway is None:
        raise ResourceNotExistsError()
    return gateway_model_to_gateway(gateway)


async def set_default_gateway(session: AsyncSession, project: ProjectModel, name: str):
    gateway = await get_project_gateway_model_by_name(session=session, project=project, name=name)
    if gateway is None:
        raise ResourceNotExistsError()
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


async def register_service_jobs(
    session: AsyncSession, project: ProjectModel, run_name: str, jobs: List[Job]
):
    # we publish only one job
    job = jobs[0]
    if job.job_spec.gateway is None:
        raise ServerClientError("Job spec has no gateway")

    gateway_name = job.job_spec.gateway.gateway_name
    if gateway_name is None:
        gateway = project.default_gateway
        if gateway is None:
            raise ResourceNotExistsError("Default gateway is not set")
    else:
        gateway = await get_project_gateway_model_by_name(
            session=session, project=project, name=gateway_name
        )
        if gateway is None:
            raise ResourceNotExistsError("Gateway does not exist")

    if gateway.gateway_compute is None:
        raise ServerClientError("Gateway has no instance associated with it")

    domain = gateway.wildcard_domain.lstrip("*.") if gateway.wildcard_domain else None
    private_bytes, public_bytes = generate_rsa_key_pair_bytes(comment=f"{project.name}/{run_name}")

    job.job_spec.gateway.gateway_name = gateway.name
    job.job_spec.gateway.ssh_key = private_bytes.decode()
    if domain is not None:
        job.job_spec.gateway.secure = True
        job.job_spec.gateway.public_port = 443
        job.job_spec.gateway.hostname = f"{run_name}.{domain}"
    else:
        job.job_spec.gateway.secure = False
        # use provided public port
        job.job_spec.gateway.hostname = gateway.gateway_compute.ip_address

    await run_async(
        configure_gateway_over_ssh,
        f"ubuntu@{gateway.gateway_compute.ip_address}",
        gateway.gateway_compute.ssh_private_key,
        public_bytes.decode(),
        [job],
    )


def gateway_model_to_gateway(gateway_model: GatewayModel) -> Gateway:
    ip_address = ""
    instance_id = ""
    if gateway_model.gateway_compute is not None:
        ip_address = gateway_model.gateway_compute.ip_address
        instance_id = gateway_model.gateway_compute.instance_id
    return Gateway(
        name=gateway_model.name,
        ip_address=ip_address,
        instance_id=instance_id,
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
            raise GatewayError("Certbot failed, ensure the domain is valid")
        if b"No such file or directory: 'certbot'" in stderr:
            raise GatewayError(
                "Certbot is not installed. Wait for gateway provisioning to finish."
            )
        raise GatewayError(
            f"Error while connecting to gateway: {stderr.decode()}\nWait for gateway provisioning to finish."
        )

    sockets = json.loads(stdout)
    for job, socket in zip(jobs, sockets):
        job.job_spec.gateway.sock_path = socket
