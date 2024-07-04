import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.server.services.pools as services_pools
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import InstanceType, Resources
from dstack._internal.core.models.pools import Instance
from dstack._internal.core.models.runs import InstanceStatus
from dstack._internal.server.models import InstanceModel
from dstack._internal.server.testing.common import create_project, create_user
from dstack._internal.utils.common import get_current_datetime


class TestGenerateInstanceName:
    @pytest.mark.asyncio
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
            hostname="hostname_test",
            status=InstanceStatus.PENDING,
            created=created,
            region="eu-west-1",
            price=1.0,
        )
        im = InstanceModel(
            id=instance_id,
            created_at=created,
            name="test_instance",
            status=InstanceStatus.PENDING,
            unreachable=False,
            project=project,
            pool=None,
            job_provisioning_data='{"ssh_proxy":null, "backend":"local","hostname":"hostname_test","region":"eu-west","price":1.0,"username":"user1","ssh_port":12345,"dockerized":false,"instance_id":"test_instance","instance_type": {"name": "instance", "resources": {"cpus": 1, "memory_mib": 512, "gpus": [], "spot": false, "disk": {"size_mib": 102400}, "description":""}}}',
            offer='{"price":"LOCAL", "price":1.0, "backend":"local", "region":"eu-west-1", "availability":"available","instance": {"name": "instance", "resources": {"cpus": 1, "memory_mib": 512, "gpus": [], "spot": false, "disk": {"size_mib": 102400}, "description":""}}}',
        )
        instance = services_pools.instance_model_to_instance(im)
        assert instance == expected_instance
