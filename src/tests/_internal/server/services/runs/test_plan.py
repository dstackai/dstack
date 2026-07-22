import copy
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import EntityReference
from dstack._internal.core.models.configurations import (
    DevEnvironmentConfiguration,
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
from dstack._internal.core.models.resources import CPUSpec, Memory, Range, ResourcesSpec
from dstack._internal.server.services.jobs import get_jobs_from_run_spec
from dstack._internal.server.services.projects import get_project_model_by_name
from dstack._internal.server.services.runs import get_plan
from dstack._internal.server.services.runs.plan import (
    _freeze_offer_identity_value,
    _get_backend_offer_identity,
    _get_backend_offers_in_fleet,
    get_backend_offers_in_run_candidate_fleets,
    get_job_plans,
    get_targeted_instance_offers,
)
from dstack._internal.server.testing.common import (
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
        )

        get_targeted_instance_offers_mock.assert_awaited_once()
        assert len(job_plans) == 1
        assert job_plans[0].total_offers == 1
        assert job_plans[0].offers == [instance_offer]


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

        assert [instance for instance, _ in offers] == [selected_1, selected_2]
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

        assert [instance for instance, _ in offers] == [selected_1, selected_2]

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
