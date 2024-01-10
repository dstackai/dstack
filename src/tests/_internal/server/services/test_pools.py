import datetime as dt
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.server.services.pools as services_pools
import dstack._internal.server.services.projects as services_projects
import dstack._internal.server.services.users as services_users
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import InstanceType, Resources
from dstack._internal.core.models.pools import Instance, Pool
from dstack._internal.core.models.runs import InstanceStatus
from dstack._internal.core.models.users import GlobalRole
from dstack._internal.server.models import InstanceModel
from dstack._internal.server.testing.common import create_project, create_user


@pytest.mark.asyncio
async def test_pool(session: AsyncSession, test_db):
    user = await create_user(session=session)
    project = await create_project(session=session, owner=user)
    pool = await services_pools.create_pool_model(
        session=session, project=project, name="test_pool"
    )
    im = InstanceModel(
        name="test_instnce",
        project=project,
        pool=pool,
        status=InstanceStatus.PENDING,
        job_provisioning_data="",
        offer="",
    )
    session.add(im)
    await session.commit()

    core_model_pool = services_pools.pool_model_to_pool(pool)
    assert core_model_pool == Pool(name="test_pool", default=True, created_at=pool.created_at)

    list_pools = await services_pools.list_project_pool(session=session, project=project)
    assert list_pools == [services_pools.pool_model_to_pool(pool)]

    list_pool_models = await services_pools.list_project_pool_models(
        session=session, project=project
    )
    assert len(list_pool_models) == 1

    pool_intances = await services_pools.get_pool_instances(session, project, "test_pool")
    assert pool_intances == [im]


def test_convert_instance():
    expected_instance = Instance(
        backend=BackendType.LOCAL,
        instance_type=InstanceType(
            name="instance", resources=Resources(cpus=1, memory_mib=512, spot=False, gpus=[])
        ),
        instance_id="test_instance",
        hostname="hostname_test",
        status=InstanceStatus.PENDING,
        price=1.0,
    )

    im = InstanceModel(
        id=str(uuid.uuid4()),
        created_at=dt.datetime.now(),
        name="test_instance",
        status=InstanceStatus.PENDING,
        project_id=str(uuid.uuid4()),
        pool=None,
        job_provisioning_data='{"backend":"local","hostname":"hostname_test","region":"eu-west","price":1.0,"username":"user1","ssh_port":12345,"dockerized":false,"instance_id":"test_instance","instance_type": {"name": "instance", "resources": {"cpus": 1, "memory_mib": 512, "gpus": [], "spot": false, "disk": {"size_mib": 102400}, "description":""}}}',
        offer='{"price":"LOCAL", "price":1.0, "backend":"local", "region":"eu-west-1", "availability":"available","instance": {"name": "instance", "resources": {"cpus": 1, "memory_mib": 512, "gpus": [], "spot": false, "disk": {"size_mib": 102400}, "description":""}}}',
    )

    instance = services_pools.instance_model_to_instance(im)
    assert instance == expected_instance


@pytest.mark.asyncio
async def test_delete_pool(session: AsyncSession, test_db):
    POOL_NAME = "test_pool"
    user = await services_users.create_user(session, "test_user", global_role=GlobalRole.ADMIN)
    project = await services_projects.create_project(session, user, "test_project")
    project_model = await services_projects.get_project_model_by_name_or_error(
        session, project.project_name
    )
    pool = await services_pools.create_pool_model(session, project_model, POOL_NAME)

    await services_pools.delete_pool(session, project_model, POOL_NAME)

    deleted_pools = await services_pools.list_deleted_pools(session, project_model)
    assert len(deleted_pools) == 1
    assert pool.name == deleted_pools[0].name


@pytest.mark.asyncio
async def test_show_pool(session: AsyncSession, test_db):
    POOL_NAME = "test_pool"
    user = await create_user(session=session)
    project = await create_project(session=session, owner=user)
    pool = await services_pools.create_pool_model(session=session, project=project, name=POOL_NAME)
    im = InstanceModel(
        name="test_instnce",
        project=project,
        pool=pool,
        status=InstanceStatus.PENDING,
        job_provisioning_data='{"backend":"local","hostname":"hostname_test","region":"eu-west","price":1.0,"username":"user1","ssh_port":12345,"dockerized":false,"instance_id":"test_instance","instance_type": {"name": "instance", "resources": {"cpus": 1, "memory_mib": 512, "gpus": [], "spot": false, "disk": {"size_mib": 102400}, "description":""}}}',
        offer='{"price":"LOCAL", "price":1.0, "backend":"local", "region":"eu-west-1", "availability":"available","instance": {"name": "instance", "resources": {"cpus": 1, "memory_mib": 512, "gpus": [], "spot": false, "disk": {"size_mib": 102400}, "description":""}}}',
    )
    session.add(im)
    await session.commit()

    instances = await services_pools.show_pool(session, project, POOL_NAME)
    assert len(instances) == 1


@pytest.mark.asyncio
async def test_get_pool_instances(session: AsyncSession, test_db):
    POOL_NAME = "test_pool"
    user = await create_user(session=session)
    project = await create_project(session=session, owner=user)
    pool = await services_pools.create_pool_model(session=session, project=project, name=POOL_NAME)
    im = InstanceModel(
        name="test_instnce",
        project=project,
        pool=pool,
        status=InstanceStatus.PENDING,
        job_provisioning_data='{"backend":"local","hostname":"hostname_test","region":"eu-west","price":1.0,"username":"user1","ssh_port":12345,"dockerized":false,"instance_id":"test_instance","instance_type": {"name": "instance", "resources": {"cpus": 1, "memory_mib": 512, "gpus": [], "spot": false, "disk": {"size_mib": 102400}, "description":""}}}',
        offer='{"price":"LOCAL", "price":1.0, "backend":"local", "region":"eu-west-1", "availability":"available","instance": {"name": "instance", "resources": {"cpus": 1, "memory_mib": 512, "gpus": [], "spot": false, "disk": {"size_mib": 102400}, "description":""}}}',
    )
    session.add(im)
    await session.commit()

    instances = await services_pools.get_pool_instances(session, project, POOL_NAME)
    assert len(instances) == 1

    empty_instances = await services_pools.get_pool_instances(session, project, f"{POOL_NAME}-0")
    assert len(empty_instances) == 0


@pytest.mark.asyncio
async def test_generate_instance_name(session: AsyncSession, test_db):
    user = await create_user(session=session)
    project = await create_project(session=session, owner=user)
    pool = await services_pools.create_pool_model(
        session=session, project=project, name="test_pool"
    )
    im = InstanceModel(
        name="test_instnce",
        project=project,
        pool=pool,
        status=InstanceStatus.PENDING,
        job_provisioning_data="",
        offer="",
    )
    session.add(im)
    await session.commit()

    name = await services_pools.generate_instance_name(
        session=session, project=project, pool_name="test_pool"
    )
    car, _, cdr = name.partition("-")
    assert len(car) > 0
    assert len(cdr) > 0
