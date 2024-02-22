import datetime as dt
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.server.services.pools as services_pools
import dstack._internal.server.services.projects as services_projects
import dstack._internal.server.services.runs as runs
import dstack._internal.server.services.users as services_users
from dstack._internal.core.models import resources
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceType,
    LaunchedInstanceInfo,
    Resources,
    SSHKey,
)
from dstack._internal.core.models.pools import Instance, Pool
from dstack._internal.core.models.profiles import Profile
from dstack._internal.core.models.runs import InstanceStatus, Requirements
from dstack._internal.core.models.users import GlobalRole
from dstack._internal.server.models import InstanceModel
from dstack._internal.server.testing.common import create_project, create_user
from dstack._internal.utils.common import get_current_datetime


class TestPoolService:
    @pytest.mark.asyncio
    async def test_pool_smoke(self, session: AsyncSession, test_db):
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
            region="",
            price=1,
            backend=BackendType.LOCAL,
        )
        session.add(im)
        await session.commit()
        await session.refresh(pool)

        core_model_pool = services_pools.pool_model_to_pool(pool)
        assert core_model_pool == Pool(
            name="test_pool",
            default=True,
            created_at=pool.created_at.replace(tzinfo=dt.timezone.utc),  # ???
            total_instances=1,
            available_instances=0,
        )

        list_pools = await services_pools.list_project_pool(session=session, project=project)
        assert list_pools == [services_pools.pool_model_to_pool(pool)]

        list_pool_models = await services_pools.list_project_pool_models(
            session=session, project=project
        )
        assert len(list_pool_models) == 1

        pool_intances = await services_pools.get_pool_instances(session, project, "test_pool")
        assert pool_intances == [im]

    @pytest.mark.asyncio
    async def test_delete_pool(self, session: AsyncSession, test_db):
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
    async def test_show_pool(self, session: AsyncSession, test_db):
        POOL_NAME = "test_pool"
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        pool = await services_pools.create_pool_model(
            session=session, project=project, name=POOL_NAME
        )
        im = InstanceModel(
            name="test_instnce",
            project=project,
            pool=pool,
            status=InstanceStatus.PENDING,
            job_provisioning_data='{"ssh_proxy":null, "backend":"local","hostname":"hostname_test","region":"eu-west","price":1.0,"username":"user1","ssh_port":12345,"dockerized":false,"instance_id":"test_instance","instance_type": {"name": "instance", "resources": {"cpus": 1, "memory_mib": 512, "gpus": [], "spot": false, "disk": {"size_mib": 102400}, "description":""}}}',
            offer='{"price":"LOCAL", "price":1.0, "backend":"local", "region":"eu-west-1", "availability":"available","instance": {"name": "instance", "resources": {"cpus": 1, "memory_mib": 512, "gpus": [], "spot": false, "disk": {"size_mib": 102400}, "description":""}}}',
            region="eu-west",
            price=1,
            backend=BackendType.LOCAL,
        )
        session.add(im)
        await session.commit()

        pool_instances = await services_pools.show_pool(session, project, POOL_NAME)
        assert len(pool_instances.instances) == 1

    @pytest.mark.asyncio
    async def test_get_pool_instances(self, session: AsyncSession, test_db):
        POOL_NAME = "test_pool"
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        pool = await services_pools.create_pool_model(
            session=session, project=project, name=POOL_NAME
        )
        im = InstanceModel(
            name="test_instnce",
            project=project,
            pool=pool,
            status=InstanceStatus.PENDING,
            job_provisioning_data='{"backend":"local","hostname":"hostname_test","region":"eu-west","price":1.0,"username":"user1","ssh_port":12345,"dockerized":false,"instance_id":"test_instance","instance_type": {"name": "instance", "resources": {"cpus": 1, "memory_mib": 512, "gpus": [], "spot": false, "disk": {"size_mib": 102400}, "description":""}}}',
            offer='{"price":"LOCAL", "price":1.0, "backend":"local", "region":"eu-west-1", "availability":"available","instance": {"name": "instance", "resources": {"cpus": 1, "memory_mib": 512, "gpus": [], "spot": false, "disk": {"size_mib": 102400}, "description":""}}}',
            region="eu-west",
            price=1,
            backend=BackendType.LOCAL,
        )
        session.add(im)
        await session.commit()

        instances = await services_pools.get_pool_instances(session, project, POOL_NAME)
        assert len(instances) == 1

        empty_instances = await services_pools.get_pool_instances(
            session, project, f"{POOL_NAME}-0"
        )
        assert len(empty_instances) == 0


class TestPoolUtils:
    @pytest.mark.asyncio
    async def test_generate_instance_name(self, session: AsyncSession, test_db):
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

    def test_convert_instance(self):
        created = get_current_datetime()
        expected_instance = Instance(
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
            id=str(uuid.uuid4()),
            created_at=created,
            name="test_instance",
            status=InstanceStatus.PENDING,
            project_id=str(uuid.uuid4()),
            pool=None,
            job_provisioning_data='{"ssh_proxy":null, "backend":"local","hostname":"hostname_test","region":"eu-west","price":1.0,"username":"user1","ssh_port":12345,"dockerized":false,"instance_id":"test_instance","instance_type": {"name": "instance", "resources": {"cpus": 1, "memory_mib": 512, "gpus": [], "spot": false, "disk": {"size_mib": 102400}, "description":""}}}',
            offer='{"price":"LOCAL", "price":1.0, "backend":"local", "region":"eu-west-1", "availability":"available","instance": {"name": "instance", "resources": {"cpus": 1, "memory_mib": 512, "gpus": [], "spot": false, "disk": {"size_mib": 102400}, "description":""}}}',
        )

        instance = services_pools.instance_model_to_instance(im)
        assert instance == expected_instance


class TestCreatePool:
    @pytest.mark.asyncio
    async def test_pool_double_name(self, session: AsyncSession, test_db):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        await services_pools.create_pool_model(session=session, project=project, name="test_pool")
        with pytest.raises(ValueError):
            await services_pools.create_pool_model(
                session=session, project=project, name="test_pool"
            )

    @pytest.mark.asyncio
    async def test_create_cloud_instance(self, session: AsyncSession, test_db):
        user = await create_user(session)
        project = await create_project(session, user)

        profile = Profile(name="test_profile")

        requirements = Requirements(resources=resources.ResourcesSpec(cpu=1), spot=True)

        offer = InstanceOfferWithAvailability(
            backend=BackendType.DATACRUNCH,
            instance=InstanceType(
                name="instance", resources=Resources(cpus=1, memory_mib=512, spot=False, gpus=[])
            ),
            region="en",
            price=0.1,
            availability=InstanceAvailability.AVAILABLE,
        )

        launched_instance = LaunchedInstanceInfo(
            instance_id="running_instance.id",
            ip_address="running_instance.ip",
            region="running_instance.location",
            ssh_port=22,
            username="root",
            dockerized=True,
            backend_data=None,
        )

        class DummyBackend:
            TYPE = BackendType.DATACRUNCH

            def compute(self):
                return self

            def create_instance(self, *args, **kwargs):
                return launched_instance

        offers = [(DummyBackend(), offer)]

        with patch("dstack._internal.server.services.runs.get_run_plan_by_requirements") as reqs:
            reqs.return_value = offers
            await runs.create_instance(
                session,
                project,
                user,
                profile=profile,
                pool_name="test_pool",
                instance_name="test_instance",
                requirements=requirements,
                ssh_key=SSHKey(public=""),
            )

        pool = await services_pools.get_pool(session, project, "test_pool")
        assert pool is not None
        instance = pool.instances[0]

        assert instance.name == "test_instance"
        assert instance.deleted == False
        assert instance.deleted_at is None

        # assert instance.job_provisioning_data == '{"backend": "datacrunch", "instance_type": {"name": "instance", "resources": {"cpus": 1, "memory_mib": 512, "gpus": [], "spot": false, "disk": {"size_mib": 102400}, "description": ""}}, "instance_id": "running_instance.id", "ssh_proxy": null, "hostname": "running_instance.ip", "region": "running_instance.location", "price": 0.1, "username": "root", "ssh_port": 22, "dockerized": true, "backend_data": null}'

        excepted_offer = (
            '{"backend": "datacrunch", "instance": {"name": "instance", "resources": '
            '{"cpus": 1, "memory_mib": 512, "gpus": [], "spot": false, "disk": '
            '{"size_mib": 102400}, "description": ""}}, "region": "en", "price": 0.1, '
            '"availability": "available", "instance_runtime": "shim"}'
        )
        assert instance.offer == excepted_offer
