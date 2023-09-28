import asyncio
from typing import List, Optional, Sequence

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.utils.random_names as random_names
from dstack._internal.core.errors import DstackError, NotFoundError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.gateways import Gateway
from dstack._internal.server.models import GatewayModel, ProjectModel
from dstack._internal.server.services.backends import (
    get_project_backend_by_type,
    get_project_backends_with_models,
)
from dstack._internal.server.utils.common import run_async


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


def gateway_model_to_gateway(gateway_model: GatewayModel) -> Gateway:
    return Gateway(
        name=gateway_model.name,
        ip_address=gateway_model.ip_address,
        instance_id=gateway_model.instance_id,
        region=gateway_model.region,
        wildcard_domain=gateway_model.wildcard_domain,
        default=gateway_model.project.default_gateway_id == gateway_model.id,
        created_at=gateway_model.created_at,
        backend=gateway_model.backend.type,
    )
