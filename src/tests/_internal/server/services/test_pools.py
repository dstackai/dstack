import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.server.services.pools as services_pools
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import InstanceStatus, InstanceType, Resources
from dstack._internal.core.models.pools import Instance
from dstack._internal.core.models.profiles import Profile
from dstack._internal.server.models import InstanceModel
from dstack._internal.server.testing.common import (
    create_instance,
    create_pool,
    create_project,
    create_user,
    get_volume,
    get_volume_configuration,
)
from dstack._internal.utils.common import get_current_datetime


class TestFilterPoolInstances:
    # TODO: Refactor filter_pool_instances to not depend on InstanceModel and simplify tests
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_all_instances(self, test_db, session: AsyncSession):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        pool = await create_pool(session=session, project=project)
        aws_instance = await create_instance(
            session=session,
            project=project,
            pool=pool,
            backend=BackendType.AWS,
        )
        runpod_instance = await create_instance(
            session=session,
            project=project,
            pool=pool,
            backend=BackendType.RUNPOD,
        )
        instances = [aws_instance, runpod_instance]
        res = services_pools.filter_pool_instances(
            pool_instances=instances,
            profile=Profile(name="test"),
        )
        assert res == instances

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_multinode_instances(self, test_db, session: AsyncSession):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        pool = await create_pool(session=session, project=project)
        aws_instance = await create_instance(
            session=session,
            project=project,
            pool=pool,
            backend=BackendType.AWS,
        )
        runpod_instance = await create_instance(
            session=session,
            project=project,
            pool=pool,
            backend=BackendType.RUNPOD,
        )
        instances = [aws_instance, runpod_instance]
        res = services_pools.filter_pool_instances(
            pool_instances=instances,
            profile=Profile(name="test"),
            multinode=True,
        )
        assert res == [aws_instance]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_volume_instances(self, test_db, session: AsyncSession):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        pool = await create_pool(session=session, project=project)
        aws_instance = await create_instance(
            session=session,
            project=project,
            pool=pool,
            backend=BackendType.AWS,
        )
        runpod_instance1 = await create_instance(
            session=session,
            project=project,
            pool=pool,
            backend=BackendType.RUNPOD,
            region="eu",
        )
        runpod_instance2 = await create_instance(
            session=session,
            project=project,
            pool=pool,
            backend=BackendType.RUNPOD,
            region="us",
        )
        instances = [aws_instance, runpod_instance1, runpod_instance2]
        res = services_pools.filter_pool_instances(
            pool_instances=instances,
            profile=Profile(name="test"),
            volumes=[
                [
                    get_volume(
                        configuration=get_volume_configuration(
                            backend=BackendType.RUNPOD, region="us"
                        )
                    )
                ]
            ],
        )
        assert res == [runpod_instance2]


class TestGenerateInstanceName:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_generates_instance_name(self, test_db, session: AsyncSession):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        pool = await services_pools.create_pool(session=session, project=project, name="test_pool")
        im = InstanceModel(
            name="test_instnce",
            project=project,
            pool=pool,
            status=InstanceStatus.PENDING,
            unreachable=False,
            job_provisioning_data="",
            offer="",
            backend=BackendType.REMOTE,
            region="",
            price=0,
        )
        session.add(im)
        await session.commit()

        name = await services_pools.generate_instance_name(
            session=session, project=project, pool_name="test_pool"
        )
        car, _, cdr = name.partition("-")
        assert len(car) > 0
        assert len(cdr) > 0


class TestInstanceModelToInstance:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_converts_instance(self, test_db, session: AsyncSession):
        project = await create_project(
            session=session,
            name="test_project",
        )
        instance_id = uuid.uuid4()
        created = get_current_datetime()
        expected_instance = Instance(
            id=instance_id,
            project_name=project.name,
            backend=BackendType.LOCAL,
            instance_type=InstanceType(
                name="instance", resources=Resources(cpus=1, memory_mib=512, spot=False, gpus=[])
            ),
            name="test_instance",
            instance_num=0,
            hostname="hostname_test",
            status=InstanceStatus.PENDING,
            created=created,
            region="eu-west-1",
            price=1.0,
            total_blocks=1,
            busy_blocks=0,
        )
        im = InstanceModel(
            id=instance_id,
            created_at=created,
            name="test_instance",
            instance_num=0,
            status=InstanceStatus.PENDING,
            unreachable=False,
            project=project,
            pool=None,
            job_provisioning_data='{"ssh_proxy":null, "backend":"local","hostname":"hostname_test","region":"eu-west","price":1.0,"username":"user1","ssh_port":12345,"dockerized":false,"instance_id":"test_instance","instance_type": {"name": "instance", "resources": {"cpus": 1, "memory_mib": 512, "gpus": [], "spot": false, "disk": {"size_mib": 102400}, "description":""}}}',
            offer='{"price":"LOCAL", "price":1.0, "backend":"local", "region":"eu-west-1", "availability":"available","instance": {"name": "instance", "resources": {"cpus": 1, "memory_mib": 512, "gpus": [], "spot": false, "disk": {"size_mib": 102400}, "description":""}}}',
            total_blocks=1,
            busy_blocks=0,
        )
        instance = services_pools.instance_model_to_instance(im)
        assert instance == expected_instance
