import copy
from unittest.mock import AsyncMock, Mock, patch

import gpuhunt
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import EntityReference
from dstack._internal.core.models.configurations import (
    DevEnvironmentConfiguration,
    NodeGroup,
    ReplicaGroup,
    ServiceConfiguration,
    TaskConfiguration,
)
from dstack._internal.core.models.fleets import FleetNodesSpec, InstanceGroupPlacement
from dstack._internal.core.models.instances import InstanceAvailability
from dstack._internal.core.models.profiles import (
    CreationPolicy,
    FleetInstanceSelector,
    InstanceHostnameSelector,
    InstanceNameSelector,
    Profile,
)
from dstack._internal.core.models.resources import CPUSpec, GPUSpec, Memory, Range, ResourcesSpec
from dstack._internal.server.services.jobs import get_jobs_from_run_spec
from dstack._internal.server.services.offers import get_matching_shared_offer
from dstack._internal.server.services.projects import get_project_model_by_name
from dstack._internal.server.services.runs import get_plan
from dstack._internal.server.services.runs.plan import (
    _freeze_offer_identity_value,
    _get_backend_offer_identity,
    _get_backend_offers_in_fleet,
    get_backend_offers_in_run_candidate_fleets,
    get_job_plans,
    get_run_profile_and_requirements_in_fleet,
    get_targeted_instance_offers,
)
from dstack._internal.server.testing.common import (
    ComputeMockSpec,
    create_export,
    create_fleet,
    create_instance,
    create_project,
    create_repo,
    create_user,
    get_fleet_spec,
    get_instance_offer_with_availability,
    get_job_provisioning_data,
    get_remote_connection_info,
    get_run_spec,
    get_ssh_fleet_configuration,
)

pytestmark = pytest.mark.usefixtures("image_config_mock")


class TestFreezeOfferIdentityValue:
    def test_normalizes_nested_mappings_and_sets(self) -> None:
        first = {
            "b": [1, {"y": InstanceAvailability.IDLE, "x": {3, 2}}],
            "a": ("z", None),
        }
        second = {
            "a": ("z", None),
            "b": [1, {"x": {2, 3}, "y": InstanceAvailability.IDLE}],
        }

        frozen_first = _freeze_offer_identity_value(first)
        frozen_second = _freeze_offer_identity_value(second)

        assert frozen_first == frozen_second
        assert hash(frozen_first) == hash(frozen_second)

    def test_get_backend_offer_identity_uses_full_offer_payload(self) -> None:
        offer = get_instance_offer_with_availability(availability=InstanceAvailability.UNKNOWN)
        offer.backend_data = {
            "region_hint": {"b": 2, "a": 1},
            "azs": ["us-east-1b", "us-east-1a"],
        }
        same_offer = copy.deepcopy(offer)
        same_offer.backend_data = {
            "azs": ["us-east-1b", "us-east-1a"],
            "region_hint": {"a": 1, "b": 2},
        }
        different_offer = copy.deepcopy(offer)
        different_offer.backend_data = {
            "azs": ["us-east-1b", "us-east-1a"],
            "region_hint": {"a": 3, "b": 2},
        }

        assert _get_backend_offer_identity(offer) == _get_backend_offer_identity(same_offer)
        assert _get_backend_offer_identity(offer) != _get_backend_offer_identity(different_offer)


class TestGetJobPlansBackendOffers:
    """
    Backend offers are requested only for `creation_policy: reuse-or-create` runs without
    an explicit `instances` selector. `get_job_plans` decides this once via `skip_backend_offers`
    and forwards it to the offer collectors.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @pytest.mark.parametrize(
        ("creation_policy", "expected_skip_backend_offers"),
        [
            (CreationPolicy.REUSE, True),
            (CreationPolicy.REUSE_OR_CREATE, False),
        ],
    )
    async def test_skips_backend_offers_by_creation_policy(
        self,
        test_db,
        session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        creation_policy: CreationPolicy,
        expected_skip_backend_offers: bool,
    ) -> None:
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(
            repo_id=repo.name,
            configuration=TaskConfiguration(
                image="debian", commands=["echo"], creation_policy=creation_policy
            ),
        )
        monkeypatch.setattr(
            "dstack._internal.server.services.runs.plan._select_candidate_fleet_models",
            AsyncMock(return_value=[Mock()]),
        )
        find_optimal_fleet_with_offers_mock = AsyncMock(return_value=(Mock(), [], []))
        monkeypatch.setattr(
            "dstack._internal.server.services.runs.plan.find_optimal_fleet_with_offers",
            find_optimal_fleet_with_offers_mock,
        )

        await get_job_plans(
            session=session,
            project=project,
            run_spec=run_spec,
            max_offers=None,
            full_offers=False,
            unallocated_resources=False,
            for_offers_only=False,
        )

        find_optimal_fleet_with_offers_mock.assert_awaited_once()
        await_args = find_optimal_fleet_with_offers_mock.await_args
        assert await_args is not None
        assert await_args.kwargs["skip_backend_offers"] is expected_skip_backend_offers

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_excludes_backend_offers_when_instances_specified(
        self,
        test_db,
        session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(
            repo_id=repo.name,
            configuration=TaskConfiguration(
                image="debian",
                commands=["echo"],
                instances=[InstanceNameSelector(name="my-fleet-0")],
            ),
        )
        instance_offer = get_instance_offer_with_availability(price=1.0)
        get_targeted_instance_offers_mock = AsyncMock(return_value=[(Mock(), instance_offer)])
        monkeypatch.setattr(
            "dstack._internal.server.services.runs.plan.get_targeted_instance_offers",
            get_targeted_instance_offers_mock,
        )

        job_plans = await get_job_plans(
            session=session,
            project=project,
            run_spec=run_spec,
            max_offers=None,
            full_offers=False,
            unallocated_resources=False,
            for_offers_only=False,
        )

        get_targeted_instance_offers_mock.assert_awaited_once()
        assert len(job_plans) == 1
        assert job_plans[0].total_offers == 1
        assert job_plans[0].offers == [instance_offer]


class TestGetJobPlansNodeGroups:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_plans_each_node_group_with_its_own_requirements(
        self,
        test_db,
        session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(
            repo_id=repo.name,
            configuration=TaskConfiguration(
                image="debian",
                groups=[
                    NodeGroup(
                        name="router",
                        nodes=1,
                        commands=["echo router"],
                        resources=ResourcesSpec(cpu=CPUSpec(count=Range[int](min=4, max=4))),
                    ),
                    NodeGroup(
                        name="prefill",
                        nodes=2,
                        commands=["echo prefill"],
                        resources=ResourcesSpec(
                            gpu=GPUSpec(name=["L40S"], count=1),
                        ),
                    ),
                ],
            ),
        )
        cpu_offer = get_instance_offer_with_availability(price=1.0)
        gpu_offer = get_instance_offer_with_availability(price=2.0, gpu_count=1, gpu_name="L40S")

        async def find_optimal_fleet_with_offers_side_effect(*, job, **kwargs):
            gpu = job.job_spec.requirements.resources.gpu
            if gpu is not None and gpu.name:
                return Mock(), [], [(Mock(), gpu_offer)]
            return Mock(), [], [(Mock(), cpu_offer)]

        monkeypatch.setattr(
            "dstack._internal.server.services.runs.plan._select_candidate_fleet_models",
            AsyncMock(return_value=[Mock()]),
        )
        find_optimal_mock = AsyncMock(side_effect=find_optimal_fleet_with_offers_side_effect)
        monkeypatch.setattr(
            "dstack._internal.server.services.runs.plan.find_optimal_fleet_with_offers",
            find_optimal_mock,
        )

        job_plans = await get_job_plans(
            session=session,
            project=project,
            run_spec=run_spec,
            max_offers=None,
            full_offers=False,
            unallocated_resources=False,
            for_offers_only=False,
        )

        assert find_optimal_mock.await_count == 2
        planned_jobs = [call.kwargs["job"] for call in find_optimal_mock.await_args_list]
        assert [j.job_spec.node_group_name for j in planned_jobs] == ["router", "prefill"]
        assert planned_jobs[0].job_spec.requirements.resources.gpu.name is None
        assert planned_jobs[1].job_spec.requirements.resources.gpu.name == ["L40S"]

        assert len(job_plans) == 3
        assert [p.job_spec.node_group_name for p in job_plans] == [
            "router",
            "prefill",
            "prefill",
        ]
        assert job_plans[0].offers == [cpu_offer]
        assert job_plans[1].offers == [gpu_offer]
        assert job_plans[2].offers == [gpu_offer]


class TestGetJobPlansReplicaGroups:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_plans_each_replica_group_with_its_own_requirements(
        self,
        test_db,
        session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(
            repo_id=repo.name,
            configuration=ServiceConfiguration(
                port=8080,
                gateway=False,
                replicas=[
                    ReplicaGroup(
                        name="gpu-group",
                        count=Range[int](min=1, max=1),
                        resources=ResourcesSpec(gpu=GPUSpec(name=["L40S"], count=1)),
                        commands=["python server.py"],
                    ),
                    ReplicaGroup(
                        name="cpu-group",
                        count=Range[int](min=1, max=1),
                        resources=ResourcesSpec(cpu=CPUSpec(count=Range[int](min=4, max=4))),
                        commands=["python router.py"],
                    ),
                ],
            ),
        )
        gpu_offer = get_instance_offer_with_availability(price=2.0, gpu_count=1, gpu_name="L40S")
        cpu_offer = get_instance_offer_with_availability(price=1.0)

        async def find_optimal_fleet_with_offers_side_effect(*, job, **kwargs):
            gpu = job.job_spec.requirements.resources.gpu
            if gpu is not None and gpu.name:
                return Mock(), [], [(Mock(), gpu_offer)]
            return Mock(), [], [(Mock(), cpu_offer)]

        monkeypatch.setattr(
            "dstack._internal.server.services.runs.plan._select_candidate_fleet_models",
            AsyncMock(return_value=[Mock()]),
        )
        find_optimal_mock = AsyncMock(side_effect=find_optimal_fleet_with_offers_side_effect)
        monkeypatch.setattr(
            "dstack._internal.server.services.runs.plan.find_optimal_fleet_with_offers",
            find_optimal_mock,
        )

        job_plans = await get_job_plans(
            session=session,
            project=project,
            run_spec=run_spec,
            max_offers=None,
            full_offers=False,
            unallocated_resources=False,
            for_offers_only=False,
        )

        assert find_optimal_mock.await_count == 2
        planned_jobs = [call.kwargs["job"] for call in find_optimal_mock.await_args_list]
        assert [j.job_spec.replica_group for j in planned_jobs] == ["gpu-group", "cpu-group"]
        assert planned_jobs[0].job_spec.requirements.resources.gpu.name == ["L40S"]
        assert planned_jobs[1].job_spec.requirements.resources.gpu.name is None

        assert len(job_plans) == 2
        assert [p.job_spec.replica_group for p in job_plans] == ["gpu-group", "cpu-group"]
        assert job_plans[0].offers == [gpu_offer]
        assert job_plans[1].offers == [cpu_offer]


class TestGetPlan:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_empty_dev_environment_with_fleet_does_not_use_targeted_instances(
        self,
        test_db,
        session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(session=session, project_id=project.id)
        await create_fleet(session=session, project=project)
        project = await get_project_model_by_name(session=session, project_name=project.name)
        assert project is not None
        select_instances_mock = AsyncMock()
        monkeypatch.setattr(
            "dstack._internal.server.services.runs.plan.select_instances_by_selectors",
            select_instances_mock,
        )
        run_spec = get_run_spec(
            repo_id=repo.name,
            configuration=DevEnvironmentConfiguration(),
        )

        await get_plan(
            session=session,
            project=project,
            user=user,
            run_spec=run_spec,
            max_offers=None,
            full_offers=False,
            unallocated_resources=False,
            for_offers_only=False,
        )

        select_instances_mock.assert_not_awaited()


class TestGetTargetedInstanceOffers:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_only_selected_instance(self, test_db, session: AsyncSession) -> None:
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(session=session, project_id=project.id)
        fleet = await create_fleet(session=session, project=project)
        await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            name="worker-0",
        )
        selected = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            name="worker-1",
        )
        run_spec = get_run_spec(
            repo_id=repo.name,
            configuration=TaskConfiguration(image="debian", commands=["echo"]),
            profile=Profile(instances=[InstanceNameSelector(name="worker-1")]),
        )
        jobs = await get_jobs_from_run_spec(run_spec=run_spec, secrets={}, replica_num=0)

        offers = await get_targeted_instance_offers(
            session=session,
            project=project,
            run_spec=run_spec,
            job=jobs[0],
            volumes=None,
            exclude_not_available=True,
        )

        assert [instance for instance, _ in offers] == [selected]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_selected_instance_by_hostname(
        self, test_db, session: AsyncSession
    ) -> None:
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(session=session, project_id=project.id)
        fleet = await create_fleet(session=session, project=project)
        await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            name="worker-0",
            remote_connection_info=get_remote_connection_info(host="192.168.1.10"),
        )
        selected = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            name="worker-1",
            remote_connection_info=get_remote_connection_info(host="192.168.1.11"),
        )
        run_spec = get_run_spec(
            repo_id=repo.name,
            configuration=TaskConfiguration(image="debian", commands=["echo"]),
            profile=Profile(instances=[InstanceHostnameSelector(hostname="192.168.1.11")]),
        )
        jobs = await get_jobs_from_run_spec(run_spec=run_spec, secrets={}, replica_num=0)

        offers = await get_targeted_instance_offers(
            session=session,
            project=project,
            run_spec=run_spec,
            job=jobs[0],
            volumes=None,
            exclude_not_available=True,
        )

        assert [instance for instance, _ in offers] == [selected]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_selected_instance_from_imported_fleet_reference(
        self, test_db, session: AsyncSession
    ) -> None:
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user, name="importer-project")
        exporter_project = await create_project(
            session=session, owner=user, name="exporter-project"
        )
        repo = await create_repo(session=session, project_id=project.id)
        local_fleet = await create_fleet(session=session, project=project, name="same-fleet")
        exported_fleet = await create_fleet(
            session=session, project=exporter_project, name="same-fleet"
        )
        await create_instance(
            session=session,
            project=project,
            fleet=local_fleet,
            instance_num=1,
            name="local-worker",
        )
        selected = await create_instance(
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
        run_spec = get_run_spec(
            repo_id=repo.name,
            configuration=TaskConfiguration(image="debian", commands=["echo"]),
            profile=Profile(
                instances=[
                    FleetInstanceSelector(
                        fleet=EntityReference.parse("exporter-project/same-fleet"),
                        instance=1,
                    )
                ]
            ),
        )
        jobs = await get_jobs_from_run_spec(run_spec=run_spec, secrets={}, replica_num=0)

        offers = await get_targeted_instance_offers(
            session=session,
            project=project,
            run_spec=run_spec,
            job=jobs[0],
            volumes=None,
            exclude_not_available=True,
        )

        assert [instance for instance, _ in offers] == [selected]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_shared_block_offer_for_selected_instance(
        self, test_db, session: AsyncSession
    ) -> None:
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(session=session, project_id=project.id)
        fleet = await create_fleet(session=session, project=project)
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            name="shared-worker",
            total_blocks=2,
            busy_blocks=1,
        )
        run_spec = get_run_spec(
            repo_id=repo.name,
            configuration=TaskConfiguration(
                image="debian",
                commands=["echo"],
                resources=ResourcesSpec(
                    cpu=CPUSpec.parse("1"),
                    memory=Range[Memory](min=Memory.parse("1GB"), max=None),
                    gpu=None,
                ),
            ),
            profile=Profile(instances=[InstanceNameSelector(name="shared-worker")]),
        )
        jobs = await get_jobs_from_run_spec(run_spec=run_spec, secrets={}, replica_num=0)

        offers = await get_targeted_instance_offers(
            session=session,
            project=project,
            run_spec=run_spec,
            job=jobs[0],
            volumes=None,
            exclude_not_available=True,
        )

        assert [selected for selected, _ in offers] == [instance]
        assert offers[0][1].blocks == 1
        assert offers[0][1].total_blocks == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_multinode_does_not_count_blocks_as_nodes(
        self, test_db, session: AsyncSession
    ) -> None:
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(session=session, project_id=project.id)
        fleet_spec = get_fleet_spec()
        fleet_spec.configuration.placement = InstanceGroupPlacement.CLUSTER
        fleet = await create_fleet(session=session, project=project, spec=fleet_spec)
        await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            name="shared-worker",
            backend=BackendType.AWS,
            total_blocks=2,
            busy_blocks=0,
        )
        run_spec = get_run_spec(
            repo_id=repo.name,
            configuration=TaskConfiguration(image="debian", nodes=2, commands=["echo"]),
            profile=Profile(instances=[InstanceNameSelector(name="shared-worker")]),
        )
        jobs = await get_jobs_from_run_spec(run_spec=run_spec, secrets={}, replica_num=0)

        offers = await get_targeted_instance_offers(
            session=session,
            project=project,
            run_spec=run_spec,
            job=jobs[0],
            volumes=None,
            exclude_not_available=True,
        )

        assert offers == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_multinode_returns_full_host_offer_per_selected_shared_instance(
        self, test_db, session: AsyncSession
    ) -> None:
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(session=session, project_id=project.id)
        fleet_spec = get_fleet_spec()
        fleet_spec.configuration.placement = InstanceGroupPlacement.CLUSTER
        fleet = await create_fleet(session=session, project=project, spec=fleet_spec)
        selected_1 = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            name="worker-0",
            backend=BackendType.REMOTE,
            total_blocks=2,
            busy_blocks=0,
        )
        selected_2 = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            name="worker-1",
            backend=BackendType.REMOTE,
            total_blocks=2,
            busy_blocks=0,
        )
        run_spec = get_run_spec(
            repo_id=repo.name,
            configuration=TaskConfiguration(
                image="debian",
                nodes=2,
                commands=["echo"],
                resources=ResourcesSpec(
                    cpu=CPUSpec.parse("1.."),
                    memory=Range[Memory](min=Memory.parse("1GB"), max=None),
                    gpu=None,
                ),
            ),
            profile=Profile(
                instances=[
                    InstanceNameSelector(name="worker-0"),
                    InstanceNameSelector(name="worker-1"),
                ]
            ),
        )
        jobs = await get_jobs_from_run_spec(run_spec=run_spec, secrets={}, replica_num=0)

        offers = await get_targeted_instance_offers(
            session=session,
            project=project,
            run_spec=run_spec,
            job=jobs[0],
            volumes=None,
            exclude_not_available=True,
        )

        # Sorted: the plan query does not order instances.
        assert sorted(instance.id for instance, _ in offers) == sorted(
            [selected_1.id, selected_2.id]
        )
        assert [offer.blocks for _, offer in offers] == [2, 2]
        assert [offer.total_blocks for _, offer in offers] == [2, 2]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_multinode_returns_selected_instances_in_same_cluster_fleet(
        self, test_db, session: AsyncSession
    ) -> None:
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(session=session, project_id=project.id)
        fleet_spec = get_fleet_spec()
        fleet_spec.configuration.placement = InstanceGroupPlacement.CLUSTER
        fleet = await create_fleet(session=session, project=project, spec=fleet_spec)
        selected_1 = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            name="worker-0",
            backend=BackendType.AWS,
            job_provisioning_data=get_job_provisioning_data(region="eu-west-1"),
        )
        selected_2 = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            name="worker-1",
            backend=BackendType.AWS,
            job_provisioning_data=get_job_provisioning_data(region="eu-west-1"),
        )
        run_spec = get_run_spec(
            repo_id=repo.name,
            configuration=TaskConfiguration(image="debian", nodes=2, commands=["echo"]),
            profile=Profile(
                instances=[
                    InstanceNameSelector(name="worker-0"),
                    InstanceNameSelector(name="worker-1"),
                ]
            ),
        )
        jobs = await get_jobs_from_run_spec(run_spec=run_spec, secrets={}, replica_num=0)

        offers = await get_targeted_instance_offers(
            session=session,
            project=project,
            run_spec=run_spec,
            job=jobs[0],
            volumes=None,
            exclude_not_available=True,
        )

        # Sorted: the plan query does not order instances.
        assert sorted(instance.id for instance, _ in offers) == sorted(
            [selected_1.id, selected_2.id]
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_multinode_requires_selected_instances_in_one_cluster_fleet(
        self, test_db, session: AsyncSession
    ) -> None:
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(session=session, project_id=project.id)
        fleet_spec = get_fleet_spec()
        fleet_spec.configuration.placement = InstanceGroupPlacement.CLUSTER
        fleet_1 = await create_fleet(session=session, project=project, spec=fleet_spec)
        fleet_2 = await create_fleet(session=session, project=project, spec=fleet_spec)
        await create_instance(
            session=session,
            project=project,
            fleet=fleet_1,
            name="worker-0",
            backend=BackendType.AWS,
        )
        await create_instance(
            session=session,
            project=project,
            fleet=fleet_2,
            name="worker-1",
            backend=BackendType.AWS,
        )
        run_spec = get_run_spec(
            repo_id=repo.name,
            configuration=TaskConfiguration(image="debian", nodes=2, commands=["echo"]),
            profile=Profile(
                instances=[
                    InstanceNameSelector(name="worker-0"),
                    InstanceNameSelector(name="worker-1"),
                ]
            ),
        )
        jobs = await get_jobs_from_run_spec(run_spec=run_spec, secrets={}, replica_num=0)

        offers = await get_targeted_instance_offers(
            session=session,
            project=project,
            run_spec=run_spec,
            job=jobs[0],
            volumes=None,
            exclude_not_available=True,
        )

        assert offers == []


class TestGetBackendOffersInRunCandidateFleets:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_skips_backend_offers_when_instances_specified(
        self, test_db, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(session=session, project_id=project.id)
        run_spec = get_run_spec(
            repo_id=repo.name,
            configuration=TaskConfiguration(image="debian", commands=["echo"]),
            profile=Profile(instances=[InstanceNameSelector(name="missing-instance")]),
        )
        jobs = await get_jobs_from_run_spec(run_spec=run_spec, secrets={}, replica_num=0)
        select_candidate_fleet_models_mock = AsyncMock()
        monkeypatch.setattr(
            "dstack._internal.server.services.runs.plan._select_candidate_fleet_models",
            select_candidate_fleet_models_mock,
        )

        offers = await get_backend_offers_in_run_candidate_fleets(
            session=session,
            project=project,
            run_spec=run_spec,
            job=jobs[0],
            volumes=None,
        )

        assert offers == []
        select_candidate_fleet_models_mock.assert_not_awaited()


class TestGetBackendOffersInFleet:
    @pytest.mark.asyncio
    async def test_ssh_blocks_fleet_keeps_old_requirement_combination_semantics(self) -> None:
        fleet_spec = get_fleet_spec(get_ssh_fleet_configuration(blocks="auto"))
        fleet_spec.configuration.resources = ResourcesSpec(
            cpu=CPUSpec.parse("4..8"),
            memory=Range[Memory](min=Memory.parse("8GB"), max=Memory.parse("32GB")),
            gpu=None,
        )
        run_spec = get_run_spec(
            repo_id="repo",
            configuration=TaskConfiguration(
                image="debian",
                commands=["echo"],
                resources=ResourcesSpec(
                    cpu=CPUSpec.parse("1"),
                    memory=Range[Memory](min=Memory.parse("2GB"), max=None),
                    gpu=None,
                ),
            ),
        )
        jobs = await get_jobs_from_run_spec(run_spec=run_spec, secrets={}, replica_num=0)

        with pytest.raises(ValueError, match="Cannot combine fleet requirements"):
            get_run_profile_and_requirements_in_fleet(
                job=jobs[0],
                run_spec=run_spec,
                fleet_spec=fleet_spec,
            )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_keeps_unconstrained_offers_for_non_empty_cluster_fleet_without_elected_master(
        self, test_db, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(session=session, project_id=project.id)
        fleet_spec = get_fleet_spec()
        fleet_spec.configuration.placement = InstanceGroupPlacement.CLUSTER
        fleet_spec.configuration.nodes = FleetNodesSpec(min=0, target=1, max=2)
        fleet = await create_fleet(session=session, project=project, spec=fleet_spec)
        await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            job_provisioning_data=get_job_provisioning_data(region="eu-west-1"),
        )
        run_spec = get_run_spec(
            repo_id=repo.name,
            configuration=TaskConfiguration(image="debian", nodes=2),
        )
        jobs = await get_jobs_from_run_spec(run_spec=run_spec, secrets={}, replica_num=0)
        get_offers_by_requirements_mock = AsyncMock()
        monkeypatch.setattr(
            "dstack._internal.server.services.runs.plan.get_offers_by_requirements",
            get_offers_by_requirements_mock,
        )
        offer = get_instance_offer_with_availability()
        backend = AsyncMock()
        get_offers_by_requirements_mock.return_value = [(backend, offer)]

        offers = await _get_backend_offers_in_fleet(
            project=project,
            fleet_model=fleet,
            run_spec=run_spec,
            job=jobs[0],
            volumes=None,
        )

        assert offers == [(backend, offer)]
        get_offers_by_requirements_mock.assert_awaited_once()
        assert (
            get_offers_by_requirements_mock.await_args.kwargs["master_job_provisioning_data"]
            is None
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_single_block_offer_when_new_capacity_can_share_growing_blocks_fleet(
        self, test_db, session: AsyncSession
    ) -> None:
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(session=session, project_id=project.id)
        fleet_spec = get_fleet_spec()
        fleet_spec.configuration.nodes = FleetNodesSpec(min=0, target=0, max=2)
        fleet_spec.configuration.blocks = "auto"
        fleet_spec.configuration.resources = ResourcesSpec(
            cpu=CPUSpec.parse("4..8"),
            memory=Range[Memory](min=Memory.parse("8GB"), max=Memory.parse("32GB")),
            gpu=None,
            disk="100GB..",
        )
        fleet = await create_fleet(session=session, project=project, spec=fleet_spec)
        run_spec = get_run_spec(
            repo_id=repo.name,
            configuration=TaskConfiguration(
                image="debian",
                commands=["echo"],
                resources=ResourcesSpec(
                    cpu=CPUSpec.parse("arm:1"),
                    memory=Range[Memory](min=Memory.parse("2GB"), max=None),
                    gpu=None,
                    disk="200GB..",
                ),
            ),
        )
        jobs = await get_jobs_from_run_spec(run_spec=run_spec, secrets={}, replica_num=0)
        offer = get_instance_offer_with_availability(cpu_count=4, memory_gib=8, disk_gib=300)
        offer.instance.resources.cpu_arch = gpuhunt.CPUArchitecture.ARM
        with (
            patch("dstack._internal.server.services.backends.get_project_backends") as m,
            patch(
                "dstack._internal.server.services.offers.get_matching_shared_offer",
                wraps=get_matching_shared_offer,
            ) as matching_shared_offer_mock,
        ):
            backend = Mock()
            backend.TYPE = BackendType.AWS
            compute_mock = Mock(spec=ComputeMockSpec)
            backend.compute.return_value = compute_mock
            compute_mock.get_offers.return_value = [offer]
            m.return_value = [backend]

            offers = await _get_backend_offers_in_fleet(
                project=project,
                fleet_model=fleet,
                run_spec=run_spec,
                job=jobs[0],
                volumes=None,
            )

        assert [
            (selected_backend, selected_offer.blocks)
            for selected_backend, selected_offer in offers
        ] == [(backend, 1)]
        assert offers[0][1].total_blocks == 4
        assert offers[0][1].instance.resources.cpus == 4
        assert offers[0][1].instance.resources.memory_mib == 8 * 1024
        queried_requirements = compute_mock.get_offers.call_args.args[0]
        shared_offer_requirements = matching_shared_offer_mock.call_args.kwargs["requirements"]
        assert queried_requirements.resources.cpu.count == Range[int](min=4, max=8)
        assert queried_requirements.resources.cpu.arch == gpuhunt.CPUArchitecture.ARM
        assert queried_requirements.resources.memory == Range[Memory](
            min=Memory.parse("8GB"),
            max=Memory.parse("32GB"),
        )
        assert queried_requirements.resources.disk.size == Range[Memory](
            min=Memory.parse("200GB"),
            max=None,
        )
        assert shared_offer_requirements.resources.cpu.count == Range[int](min=1, max=1)
        assert shared_offer_requirements.resources.cpu.arch == gpuhunt.CPUArchitecture.ARM
        assert shared_offer_requirements.resources.memory == Range[Memory](
            min=Memory.parse("2GB"),
            max=None,
        )
        assert shared_offer_requirements.resources.disk.size == Range[Memory](
            min=Memory.parse("200GB"),
            max=None,
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_multi_block_offer_when_new_capacity_needs_more_than_one_block(
        self, test_db, session: AsyncSession
    ) -> None:
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(session=session, project_id=project.id)
        fleet_spec = get_fleet_spec()
        fleet_spec.configuration.nodes = FleetNodesSpec(min=0, target=0, max=2)
        fleet_spec.configuration.blocks = "auto"
        fleet_spec.configuration.resources = ResourcesSpec(
            cpu=CPUSpec.parse("4..8"),
            memory=Range[Memory](min=Memory.parse("8GB"), max=Memory.parse("32GB")),
            gpu=None,
        )
        fleet = await create_fleet(session=session, project=project, spec=fleet_spec)
        run_spec = get_run_spec(
            repo_id=repo.name,
            configuration=TaskConfiguration(
                image="debian",
                commands=["echo"],
                resources=ResourcesSpec(
                    cpu=CPUSpec.parse("2"),
                    memory=Range[Memory](min=Memory.parse("3GB"), max=None),
                    gpu=None,
                ),
            ),
        )
        jobs = await get_jobs_from_run_spec(run_spec=run_spec, secrets={}, replica_num=0)
        offer = get_instance_offer_with_availability(cpu_count=4, memory_gib=8)
        with (
            patch("dstack._internal.server.services.backends.get_project_backends") as m,
            patch(
                "dstack._internal.server.services.offers.get_matching_shared_offer",
                wraps=get_matching_shared_offer,
            ) as matching_shared_offer_mock,
        ):
            backend = Mock()
            backend.TYPE = BackendType.AWS
            compute_mock = Mock(spec=ComputeMockSpec)
            backend.compute.return_value = compute_mock
            compute_mock.get_offers.return_value = [offer]
            m.return_value = [backend]

            offers = await _get_backend_offers_in_fleet(
                project=project,
                fleet_model=fleet,
                run_spec=run_spec,
                job=jobs[0],
                volumes=None,
            )

        assert [
            (selected_backend, selected_offer.blocks)
            for selected_backend, selected_offer in offers
        ] == [(backend, 2)]
        assert offers[0][1].total_blocks == 4
        assert offers[0][1].instance.resources.cpus == 4
        assert offers[0][1].instance.resources.memory_mib == 8 * 1024
        queried_requirements = compute_mock.get_offers.call_args.args[0]
        shared_offer_requirements = matching_shared_offer_mock.call_args.kwargs["requirements"]
        assert queried_requirements.resources.cpu.count == Range[int](min=4, max=8)
        assert queried_requirements.resources.memory == Range[Memory](
            min=Memory.parse("8GB"),
            max=Memory.parse("32GB"),
        )
        assert shared_offer_requirements.resources.cpu.count == Range[int](min=2, max=2)
        assert shared_offer_requirements.resources.memory == Range[Memory](
            min=Memory.parse("3GB"),
            max=None,
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_excludes_non_create_backends_for_cloud_blocks_fleet(
        self, test_db, session: AsyncSession
    ) -> None:
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(session=session, project_id=project.id)
        fleet_spec = get_fleet_spec()
        fleet_spec.configuration.nodes = FleetNodesSpec(min=0, target=0, max=2)
        fleet_spec.configuration.blocks = "auto"
        fleet_spec.configuration.resources = ResourcesSpec(
            cpu=CPUSpec.parse("4..8"),
            memory=Range[Memory](min=Memory.parse("8GB"), max=Memory.parse("32GB")),
            gpu=None,
        )
        fleet = await create_fleet(session=session, project=project, spec=fleet_spec)
        run_spec = get_run_spec(
            repo_id=repo.name,
            configuration=TaskConfiguration(
                image="debian",
                commands=["echo"],
                resources=ResourcesSpec(
                    cpu=CPUSpec.parse("1"),
                    memory=Range[Memory](min=Memory.parse("2GB"), max=None),
                    gpu=None,
                ),
            ),
        )
        jobs = await get_jobs_from_run_spec(run_spec=run_spec, secrets={}, replica_num=0)

        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            aws_backend = Mock()
            aws_backend.TYPE = BackendType.AWS
            aws_compute_mock = Mock(spec=ComputeMockSpec)
            aws_backend.compute.return_value = aws_compute_mock
            aws_offer = get_instance_offer_with_availability(
                backend=BackendType.AWS, cpu_count=4, memory_gib=8
            )
            aws_compute_mock.get_offers.return_value = [aws_offer]

            kubernetes_backend = Mock()
            kubernetes_backend.TYPE = BackendType.KUBERNETES
            kubernetes_compute_mock = Mock()
            kubernetes_backend.compute.return_value = kubernetes_compute_mock
            kubernetes_offer = get_instance_offer_with_availability(
                backend=BackendType.KUBERNETES,
                region="",
                cpu_count=4,
                memory_gib=8,
            )
            kubernetes_compute_mock.get_offers.return_value = [kubernetes_offer]

            m.return_value = [aws_backend, kubernetes_backend]

            offers = await _get_backend_offers_in_fleet(
                project=project,
                fleet_model=fleet,
                run_spec=run_spec,
                job=jobs[0],
                volumes=None,
            )

        assert [backend.TYPE for backend, _ in offers] == [BackendType.AWS]
        aws_compute_mock.get_offers.assert_called_once()
        kubernetes_compute_mock.get_offers.assert_not_called()
