import uuid
from unittest.mock import Mock, call

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession

import dstack._internal.server.services.instances as instances_services
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.health import HealthStatus
from dstack._internal.core.models.instances import (
    Instance,
    InstanceStatus,
    InstanceTerminationReason,
    InstanceType,
    Resources,
)
from dstack._internal.core.models.profiles import (
    FleetInstanceSelector,
    InstanceHostnameSelector,
    InstanceNameSelector,
    Profile,
)
from dstack._internal.core.models.runs import JobStatus
from dstack._internal.server.models import InstanceModel
from dstack._internal.server.schemas.runner import TaskListItem, TaskListResponse, TaskStatus
from dstack._internal.server.services.runner.client import ShimClient
from dstack._internal.server.testing.common import (
    create_export,
    create_fleet,
    create_instance,
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_job_provisioning_data,
    get_kubernetes_volume_configuration,
    get_remote_connection_info,
    get_volume,
    get_volume_configuration,
    get_volume_provisioning_data,
    list_events,
)
from dstack._internal.utils.common import get_current_datetime


class TestSwitchInstanceStatus:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_includes_termination_reason_in_event_messages_only_once(
        self, test_db, session: AsyncSession
    ) -> None:
        project = await create_project(session=session)
        instance = await create_instance(
            session=session, project=project, status=InstanceStatus.PENDING
        )
        instance.termination_reason = InstanceTerminationReason.ERROR
        instance.termination_reason_message = "Some err"
        instances_services.switch_instance_status(session, instance, InstanceStatus.TERMINATING)
        instances_services.switch_instance_status(session, instance, InstanceStatus.TERMINATED)
        await session.commit()
        events = await list_events(session)
        assert len(events) == 2
        assert {e.message for e in events} == {
            "Instance status changed PENDING -> TERMINATING. Termination reason: ERROR (Some err)",
            # Do not duplicate the termination reason in the second event
            "Instance status changed TERMINATING -> TERMINATED",
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_includes_termination_reason_in_event_message_when_switching_directly_to_terminated(
        self, test_db, session: AsyncSession
    ) -> None:
        project = await create_project(session=session)
        instance = await create_instance(
            session=session, project=project, status=InstanceStatus.PENDING
        )
        instance.termination_reason = InstanceTerminationReason.ERROR
        instance.termination_reason_message = "Some err"
        instances_services.switch_instance_status(session, instance, InstanceStatus.TERMINATED)
        await session.commit()
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == (
            "Instance status changed PENDING -> TERMINATED. Termination reason: ERROR (Some err)"
        )


class TestFilterInstances:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_all_instances(self, test_db, session: AsyncSession):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        aws_instance = await create_instance(
            session=session,
            project=project,
            backend=BackendType.AWS,
        )
        runpod_instance = await create_instance(
            session=session,
            project=project,
            backend=BackendType.RUNPOD,
        )
        instances = [aws_instance, runpod_instance]
        res = instances_services.filter_instances(
            instances=instances,
            profile=Profile(name="test"),
        )
        assert res == instances

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_multinode_instances(self, test_db, session: AsyncSession):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        aws_instance = await create_instance(
            session=session,
            project=project,
            backend=BackendType.AWS,
        )
        vastai_instance = await create_instance(
            session=session,
            project=project,
            backend=BackendType.VASTAI,
        )
        instances = [aws_instance, vastai_instance]
        res = instances_services.filter_instances(
            instances=instances,
            profile=Profile(name="test"),
            multinode=True,
        )
        assert res == [aws_instance]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_volume_instances(self, test_db, session: AsyncSession):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        aws_instance = await create_instance(
            session=session,
            project=project,
            backend=BackendType.AWS,
        )
        runpod_instance1 = await create_instance(
            session=session,
            project=project,
            backend=BackendType.RUNPOD,
            region="eu",
        )
        runpod_instance2 = await create_instance(
            session=session,
            project=project,
            backend=BackendType.RUNPOD,
            region="us",
        )
        instances = [aws_instance, runpod_instance1, runpod_instance2]
        res = instances_services.filter_instances(
            instances=instances,
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

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_volume_instances_with_az(self, test_db, session: AsyncSession):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        aws_instance_1 = await create_instance(
            session=session,
            project=project,
            backend=BackendType.AWS,
            region="us-1",
            availability_zone="us-1a",
        )
        aws_instance_2 = await create_instance(
            session=session,
            project=project,
            backend=BackendType.AWS,
            region="us-1",
            availability_zone="us-1b",
        )
        gcp_instance = await create_instance(
            session=session,
            project=project,
            backend=BackendType.GCP,
            region="us-1",
            availability_zone="us-1b",
        )
        instances = [aws_instance_1, aws_instance_2, gcp_instance]
        volume = get_volume(
            configuration=get_volume_configuration(backend=BackendType.AWS, region="us-1"),
            provisioning_data=get_volume_provisioning_data(
                backend=BackendType.AWS, availability_zone="us-1b"
            ),
        )
        res = instances_services.filter_instances(
            instances=instances,
            profile=Profile(name="test"),
            volumes=[[volume]],
        )
        assert res == [aws_instance_2]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_filters_by_instance_name(self, test_db, session: AsyncSession):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        instance0 = await create_instance(
            session=session,
            project=project,
            instance_num=0,
            name="my-cluster-0",
        )
        instance1 = await create_instance(
            session=session,
            project=project,
            instance_num=1,
            name="my-cluster-1",
        )
        instances = [instance0, instance1]
        res = instances_services.filter_instances(
            instances=instances,
            profile=Profile(name="test", instances=[InstanceNameSelector(name="my-cluster-1")]),
        )
        assert res == [instance1]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_filters_by_instance_name_case_insensitive(self, test_db, session: AsyncSession):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        instance0 = await create_instance(
            session=session,
            project=project,
            name="my-cluster-0",
        )
        res = instances_services.filter_instances(
            instances=[instance0],
            profile=Profile(name="test", instances=[InstanceNameSelector(name="MY-CLUSTER-0")]),
        )
        assert res == [instance0]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_filters_by_hostname(self, test_db, session: AsyncSession):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        instance0 = await create_instance(
            session=session,
            project=project,
            name="my-cluster-0",
            job_provisioning_data=get_job_provisioning_data(hostname="10.0.0.7"),
        )
        instance1 = await create_instance(
            session=session,
            project=project,
            name="my-cluster-1",
            job_provisioning_data=get_job_provisioning_data(hostname="10.0.0.8"),
        )
        instances = [instance0, instance1]
        res = instances_services.filter_instances(
            instances=instances,
            profile=Profile(
                name="test",
                instances=[InstanceHostnameSelector(hostname="10.0.0.8")],
            ),
        )
        assert res == [instance1]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_filters_by_internal_ip(self, test_db, session: AsyncSession):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        instance0 = await create_instance(
            session=session,
            project=project,
            name="my-cluster-0",
            job_provisioning_data=get_job_provisioning_data(
                hostname="203.0.113.7", internal_ip="10.0.0.7"
            ),
        )
        instance1 = await create_instance(
            session=session,
            project=project,
            name="my-cluster-1",
            job_provisioning_data=get_job_provisioning_data(
                hostname="203.0.113.8", internal_ip="10.0.0.8"
            ),
        )
        res = instances_services.filter_instances(
            instances=[instance0, instance1],
            profile=Profile(
                name="test",
                instances=[InstanceHostnameSelector(hostname="10.0.0.8")],
            ),
        )
        assert res == [instance1]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_string_selector_does_not_match_hostname(self, test_db, session: AsyncSession):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        instance = await create_instance(
            session=session,
            project=project,
            name="my-cluster-0",
            job_provisioning_data=get_job_provisioning_data(hostname="10.0.0.8"),
        )
        res = instances_services.filter_instances(
            instances=[instance],
            profile=Profile.parse_obj({"name": "test", "instances": ["10.0.0.8"]}),
        )
        assert res == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_filters_by_ssh_host(self, test_db, session: AsyncSession):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        instance0 = await create_instance(
            session=session,
            project=project,
            name="my-cluster-0",
            remote_connection_info=get_remote_connection_info(host="192.168.1.10"),
        )
        instance1 = await create_instance(
            session=session,
            project=project,
            name="my-cluster-1",
            remote_connection_info=get_remote_connection_info(host="192.168.1.11"),
        )
        instances = [instance0, instance1]
        res = instances_services.filter_instances(
            instances=instances,
            profile=Profile(
                name="test",
                instances=[InstanceHostnameSelector(hostname="192.168.1.11")],
            ),
        )
        assert res == [instance1]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_filters_by_fleet_and_instance_number(self, test_db, session: AsyncSession):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        fleet = await create_fleet(session=session, project=project, name="my-fleet")
        instance0 = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            instance_num=0,
            name="worker-a",
        )
        instance1 = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            instance_num=1,
            name="worker-b",
        )
        res = instances_services.filter_instances(
            instances=[instance0, instance1],
            profile=Profile(
                name="test",
                instances=[FleetInstanceSelector(fleet="my-fleet", instance=1)],
            ),
        )
        assert res == [instance1]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_filters_by_fleet_and_instance_number_without_loading_instance_fleet(
        self, test_db, session: AsyncSession
    ):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        fleet = await create_fleet(session=session, project=project, name="my-fleet")
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            instance_num=1,
            name="worker-b",
        )
        session.expire(instance, ["fleet"])
        assert "fleet" in sa_inspect(instance).unloaded

        res = instances_services.filter_instances(
            instances=[instance],
            profile=Profile(
                name="test",
                instances=[FleetInstanceSelector(fleet="my-fleet", instance=1)],
            ),
            fleet=fleet,
        )
        assert res == [instance]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @pytest.mark.parametrize(
        ("selector", "expected_instance_name"),
        [
            ("same-fleet", "local-worker"),
            ("exporter-project/same-fleet", "exported-worker"),
        ],
    )
    async def test_fleet_selector_respects_project_reference(
        self,
        test_db,
        session: AsyncSession,
        selector: str,
        expected_instance_name: str,
    ):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user, name="importer-project")
        exporter_project = await create_project(
            session=session, owner=user, name="exporter-project"
        )
        local_fleet = await create_fleet(session=session, project=project, name="same-fleet")
        exported_fleet = await create_fleet(
            session=session, project=exporter_project, name="same-fleet"
        )
        local_instance = await create_instance(
            session=session,
            project=project,
            fleet=local_fleet,
            instance_num=1,
            name="local-worker",
        )
        exported_instance = await create_instance(
            session=session,
            project=exporter_project,
            fleet=exported_fleet,
            instance_num=1,
            name="exported-worker",
        )
        await create_export(
            session=session,
            exporter_project=exporter_project,
            importer_projects=[project],
            exported_fleets=[exported_fleet],
        )

        res = instances_services.filter_instances(
            instances=[local_instance, exported_instance],
            profile=Profile(
                name="test",
                instances=[FleetInstanceSelector(fleet=selector, instance=1)],
            ),
            project=project,
        )

        assert [i.name for i in res] == [expected_instance_name]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_no_instances_selector_returns_all(self, test_db, session: AsyncSession):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        instance0 = await create_instance(session=session, project=project, name="my-cluster-0")
        instance1 = await create_instance(session=session, project=project, name="my-cluster-1")
        instances = [instance0, instance1]
        res = instances_services.filter_instances(
            instances=instances,
            profile=Profile(name="test", instances=None),
        )
        assert res == instances

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_filters_by_instance_name_for_multinode(self, test_db, session: AsyncSession):
        # Regression: the selector must also be applied on the multinode filter path.
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        instance0 = await create_instance(
            session=session,
            project=project,
            backend=BackendType.AWS,
            name="my-fleet-0",
        )
        instance1 = await create_instance(
            session=session,
            project=project,
            backend=BackendType.AWS,
            name="my-fleet-1",
        )
        res = instances_services.filter_instances(
            instances=[instance0, instance1],
            profile=Profile(name="test", instances=[InstanceNameSelector(name="my-fleet-1")]),
            multinode=True,
        )
        assert res == [instance1]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_filters_by_instance_name_for_shared(self, test_db, session: AsyncSession):
        # Regression: the selector must also be applied on the shared-instances filter path.
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        instance0 = await create_instance(
            session=session,
            project=project,
            name="my-fleet-0",
            total_blocks=2,
        )
        instance1 = await create_instance(
            session=session,
            project=project,
            name="my-fleet-1",
            total_blocks=2,
        )
        res = instances_services.filter_instances(
            instances=[instance0, instance1],
            profile=Profile(name="test", instances=[InstanceNameSelector(name="my-fleet-1")]),
            shared=True,
        )
        assert res == [instance1]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_volume_instances_without_region(self, test_db, session: AsyncSession):
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        aws_instance = await create_instance(
            session=session,
            project=project,
            backend=BackendType.AWS,
        )
        # Kubernetes does not support "create instance" feature, but for the sake of this test
        # it does not matter
        kubernetes_instance = await create_instance(
            session=session,
            project=project,
            backend=BackendType.KUBERNETES,
        )
        instances = [aws_instance, kubernetes_instance]
        volume = get_volume(
            configuration=get_kubernetes_volume_configuration(),
            provisioning_data=get_volume_provisioning_data(
                backend=BackendType.KUBERNETES, availability_zone=None
            ),
        )
        res = instances_services.filter_instances(
            instances=instances,
            profile=Profile(name="test"),
            volumes=[[volume]],
        )
        assert res == [kubernetes_instance]


@pytest.mark.asyncio
@pytest.mark.usefixtures("image_config_mock")
@pytest.mark.usefixtures("turn_off_keep_shim_tasks_setting")
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestRemoveDanglingTasks:
    @pytest.fixture
    def turn_off_keep_shim_tasks_setting(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("dstack._internal.server.settings.SERVER_KEEP_SHIM_TASKS", False)

    async def test_terminates_and_removes_dangling_tasks(
        self, test_db, session: AsyncSession
    ) -> None:
        user = await create_user(session=session)
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
        )
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            instance=instance,
        )
        dangling_task_id_1 = "fe138b77-d0b1-49d3-8c9f-2dfe78ece727"
        dangling_task_id_2 = "8b016a75-41de-44f1-91ff-c9b63d2caa1d"
        shim_client_mock = Mock(spec_set=ShimClient)
        shim_client_mock.is_api_v2_supported.return_value = True
        shim_client_mock.list_tasks.return_value = TaskListResponse(
            tasks=[
                TaskListItem(id=str(job.id), status=TaskStatus.RUNNING),
                TaskListItem(id=dangling_task_id_1, status=TaskStatus.RUNNING),
                TaskListItem(id=dangling_task_id_2, status=TaskStatus.TERMINATED),
            ]
        )
        await session.refresh(instance, attribute_names=["jobs"])

        instances_services.remove_dangling_tasks_from_instance(shim_client_mock, instance)

        await session.refresh(instance)
        assert instance.status == InstanceStatus.BUSY

        shim_client_mock.terminate_task.assert_called_once_with(
            task_id=dangling_task_id_1,
            reason=None,
            message=None,
            timeout=0,
        )
        assert shim_client_mock.remove_task.call_count == 2
        shim_client_mock.remove_task.assert_has_calls(
            [call(task_id=dangling_task_id_1), call(task_id=dangling_task_id_2)]
        )

    async def test_terminates_and_removes_dangling_tasks_legacy_shim(
        self, test_db, session: AsyncSession
    ) -> None:
        user = await create_user(session=session)
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.BUSY,
        )
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
        )
        job = await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            instance=instance,
        )
        dangling_task_id_1 = "fe138b77-d0b1-49d3-8c9f-2dfe78ece727"
        dangling_task_id_2 = "8b016a75-41de-44f1-91ff-c9b63d2caa1d"
        shim_client_mock = Mock(spec_set=ShimClient)
        shim_client_mock.is_api_v2_supported.return_value = True
        shim_client_mock.list_tasks.return_value = TaskListResponse(
            ids=[str(job.id), dangling_task_id_1, dangling_task_id_2]
        )
        await session.refresh(instance, attribute_names=["jobs"])

        instances_services.remove_dangling_tasks_from_instance(shim_client_mock, instance)

        await session.refresh(instance)
        assert instance.status == InstanceStatus.BUSY

        assert shim_client_mock.terminate_task.call_count == 2
        shim_client_mock.terminate_task.assert_has_calls(
            [
                call(task_id=dangling_task_id_1, reason=None, message=None, timeout=0),
                call(task_id=dangling_task_id_2, reason=None, message=None, timeout=0),
            ]
        )
        assert shim_client_mock.remove_task.call_count == 2
        shim_client_mock.remove_task.assert_has_calls(
            [call(task_id=dangling_task_id_1), call(task_id=dangling_task_id_2)]
        )


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
            unreachable=False,
            health_status=HealthStatus.WARNING,
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
            health=HealthStatus.WARNING,
            project=project,
            job_provisioning_data='{"ssh_proxy":null, "backend":"local","hostname":"hostname_test","region":"eu-west","price":1.0,"username":"user1","ssh_port":12345,"dockerized":false,"instance_id":"test_instance","instance_type": {"name": "instance", "resources": {"cpus": 1, "memory_mib": 512, "gpus": [], "spot": false, "disk": {"size_mib": 102400}, "description":""}}}',
            offer='{"price":"LOCAL", "price":1.0, "backend":"local", "region":"eu-west-1", "availability":"available","instance": {"name": "instance", "resources": {"cpus": 1, "memory_mib": 512, "gpus": [], "spot": false, "disk": {"size_mib": 102400}, "description":""}}}',
            total_blocks=1,
            busy_blocks=0,
        )
        instance = instances_services.instance_model_to_instance(im)
        assert instance == expected_instance
