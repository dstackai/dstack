import datetime as dt
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import InstanceType, Resources
from dstack._internal.core.models.pool import Instance, Pool
from dstack._internal.server.models import InstanceModel, PoolModel
from dstack._internal.server.services import pool as services_pool
from dstack._internal.server.testing.common import create_project, create_user


@pytest.mark.asyncio
async def test_pool(session: AsyncSession, test_db):
    user = await create_user(session=session)
    project = await create_project(session=session, owner=user)
    pool = await services_pool.create_pool_model(
        session=session, project=project, name="test_pool"
    )
    im = InstanceModel(
        name="test_instnce",
        project=project,
        pool=pool,
        job_provisioning_data="",
        offer="",
    )
    session.add(im)
    await session.commit()

    core_model_pool = services_pool.pool_model_to_pool(pool)
    assert core_model_pool == Pool(name="test_pool", default=True, created_at=pool.created_at)

    list_pools = await services_pool.list_project_pool(session=session, project=project)
    assert list_pools == [services_pool.pool_model_to_pool(pool)]

    list_pool_models = await services_pool.list_project_pool_models(
        session=session, project=project
    )
    assert len(list_pool_models) == 1

    pool_intances = await services_pool.get_pool_instances(session=session, pool_name="test_pool")
    assert pool_intances == [im]


def test_convert_instance():
    expected_instance = Instance(
        backend=BackendType.LOCAL,
        instance_type=InstanceType(
            name="instance", resources=Resources(cpus=1, memory_mib=512, spot=False, gpus=[])
        ),
        instance_id="test_instance",
        hostname="hostname_test",
        price=1.0,
    )

    im = InstanceModel(
        id=str(uuid.uuid4()),
        created_at=dt.datetime.now(),
        name="test_instance",
        project_id=str(uuid.uuid4()),
        pool=None,
        job_provisioning_data='{"backend":"local","hostname":"hostname_test","region":"eu-west","price":1.0,"username":"user1","ssh_port":12345,"dockerized":false,"instance_id":"test_instance","instance_type": {"name": "instance", "resources": {"cpus": 1, "memory_mib": 512, "gpus": [], "spot": false, "disk": {"size_mib": 102400}, "description":""}}}',
        offer='{"price":"LOCAL", "price":1.0, "backend":"local", "region":"eu-west-1", "availability":"available","instance": {"name": "instance", "resources": {"cpus": 1, "memory_mib": 512, "gpus": [], "spot": false, "disk": {"size_mib": 102400}, "description":""}}}',
    )

    instance = services_pool.instance_model_to_instance(im)
    assert instance == expected_instance


@pytest.mark.asyncio
async def test_delete_pool(session: AsyncSession, test_db):
    user = await create_user(session=session)
    project = await create_project(session=session, owner=user)
    pool = await services_pool.create_pool_model(
        session=session, project=project, name="test_pool"
    )
    im = InstanceModel(
        name="test_instnce",
        project=project,
        pool=pool,
        job_provisioning_data="",
        offer="",
    )
    session.add(im)
    await session.commit()

    await services_pool.delete_pool(session=session, project=project, pool_name="test_pool")


# async def delete_pool(session: AsyncSession, project: ProjectModel, pool_name: str):
#     """delete the pool and set the default pool to project"""

#     default_pool: Optional[PoolModel] = None
#     default_pool_removed = False

#     for pool in await list_project_pool_models(session=session, project=project):
#         if pool.name == DEFAULT_POOL_NAME:
#             default_pool = pool

#         if pool_name == pool.name:
#             if project.default_pool_id == pool.id:
#                 default_pool_removed = True
#             await session.delete(pool)

#     if default_pool_removed:
#         if default_pool is not None:
#             project.default_pool = default_pool
#         else:
#             await create_pool_model(session, project, DEFAULT_POOL_NAME)

#     await session.commit()


@pytest.mark.asyncio
async def test_show_pool(session: AsyncSession, test_db):
    POOL_NAME = "test_pool"
    user = await create_user(session=session)
    project = await create_project(session=session, owner=user)
    pool = await services_pool.create_pool_model(session=session, project=project, name=POOL_NAME)
    im = InstanceModel(
        name="test_instnce",
        project=project,
        pool=pool,
        job_provisioning_data='{"backend":"local","hostname":"hostname_test","region":"eu-west","price":1.0,"username":"user1","ssh_port":12345,"dockerized":false,"instance_id":"test_instance","instance_type": {"name": "instance", "resources": {"cpus": 1, "memory_mib": 512, "gpus": [], "spot": false, "disk": {"size_mib": 102400}, "description":""}}}',
        offer='{"price":"LOCAL", "price":1.0, "backend":"local", "region":"eu-west-1", "availability":"available","instance": {"name": "instance", "resources": {"cpus": 1, "memory_mib": 512, "gpus": [], "spot": false, "disk": {"size_mib": 102400}, "description":""}}}',
    )
    session.add(im)
    await session.commit()

    instances = await services_pool.show_pool(session, project, POOL_NAME)
    assert len(instances) == 1


@pytest.mark.asyncio
async def test_get_pool_instances(session: AsyncSession, test_db):
    POOL_NAME = "test_pool"
    user = await create_user(session=session)
    project = await create_project(session=session, owner=user)
    pool = await services_pool.create_pool_model(session=session, project=project, name=POOL_NAME)
    im = InstanceModel(
        name="test_instnce",
        project=project,
        pool=pool,
        job_provisioning_data='{"backend":"local","hostname":"hostname_test","region":"eu-west","price":1.0,"username":"user1","ssh_port":12345,"dockerized":false,"instance_id":"test_instance","instance_type": {"name": "instance", "resources": {"cpus": 1, "memory_mib": 512, "gpus": [], "spot": false, "disk": {"size_mib": 102400}, "description":""}}}',
        offer='{"price":"LOCAL", "price":1.0, "backend":"local", "region":"eu-west-1", "availability":"available","instance": {"name": "instance", "resources": {"cpus": 1, "memory_mib": 512, "gpus": [], "spot": false, "disk": {"size_mib": 102400}, "description":""}}}',
    )
    session.add(im)
    await session.commit()

    instances = await services_pool.get_pool_instances(session, POOL_NAME)
    assert len(instances) == 1

    empty_instances = await services_pool.get_pool_instances(session, f"{POOL_NAME}-0")
    assert len(empty_instances) == 0


@pytest.mark.asyncio
async def test_generate_instance_name(session: AsyncSession, test_db):
    user = await create_user(session=session)
    project = await create_project(session=session, owner=user)
    pool = await services_pool.create_pool_model(
        session=session, project=project, name="test_pool"
    )
    im = InstanceModel(
        name="test_instnce",
        project=project,
        pool=pool,
        job_provisioning_data="",
        offer="",
    )
    session.add(im)
    await session.commit()

    name = await services_pool.generate_instance_name(
        session=session, project=project, pool_name="test_pool"
    )
    car, _, cdr = name.partition("-")
    assert len(car) > 0
    assert len(cdr) > 0
