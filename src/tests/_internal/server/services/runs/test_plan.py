import copy
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.configurations import TaskConfiguration
from dstack._internal.core.models.fleets import FleetNodesSpec, InstanceGroupPlacement
from dstack._internal.core.models.instances import InstanceAvailability
from dstack._internal.core.models.profiles import (
    CreationPolicy,
    FleetInstanceSelector,
    InstanceNameSelector,
    Profile,
)
from dstack._internal.server.services.jobs import get_jobs_from_run_spec
from dstack._internal.server.services.runs.plan import (
    _freeze_offer_identity_value,
    _get_backend_offer_identity,
    _get_backend_offers_in_fleet,
    _get_job_plan,
    find_optimal_fleet_with_offers,
    get_backend_offers_in_run_candidate_fleets,
    get_run_candidate_fleet_models_filters,
    select_run_candidate_fleet_models_with_filters,
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


class TestGetJobPlan:
    @pytest.mark.asyncio
    async def test_includes_backend_offers_by_default(self) -> None:
        run_spec = get_run_spec(
            repo_id="test-repo",
            configuration=TaskConfiguration(image="debian", commands=["echo"]),
        )
        jobs = await get_jobs_from_run_spec(run_spec=run_spec, secrets={}, replica_num=0)
        instance_offer = get_instance_offer_with_availability()
        backend_offer = get_instance_offer_with_availability()

        job_plan = _get_job_plan(
            instance_offers=[(None, instance_offer)],
            backend_offers=[(None, backend_offer)],
            profile=Profile(name="default", creation_policy=CreationPolicy.REUSE_OR_CREATE),
            job=jobs[0],
            max_offers=None,
        )

        assert job_plan.total_offers == 2

    @pytest.mark.asyncio
    async def test_excludes_backend_offers_when_instances_specified(self) -> None:
        run_spec = get_run_spec(
            repo_id="test-repo",
            configuration=TaskConfiguration(image="debian", commands=["echo"]),
        )
        jobs = await get_jobs_from_run_spec(run_spec=run_spec, secrets={}, replica_num=0)
        instance_offer = get_instance_offer_with_availability()
        backend_offer = get_instance_offer_with_availability()

        job_plan = _get_job_plan(
            instance_offers=[(None, instance_offer)],
            backend_offers=[(None, backend_offer)],
            profile=Profile(
                name="default",
                creation_policy=CreationPolicy.REUSE_OR_CREATE,
                instances=[InstanceNameSelector(name="my-fleet-0")],
            ),
            job=jobs[0],
            max_offers=None,
        )

        assert job_plan.total_offers == 1
        assert job_plan.offers == [instance_offer]


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


class TestSelectRunCandidateFleetModelsWithFilters:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @pytest.mark.parametrize(
        ("selector", "expected_fleet_project_name"),
        [
            ("same-fleet", "importer-project"),
            ("exporter-project/same-fleet", "exporter-project"),
        ],
    )
    async def test_fleet_instance_selector_narrows_candidate_fleets(
        self,
        test_db,
        session: AsyncSession,
        selector: str,
        expected_fleet_project_name: str,
    ) -> None:
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user, name="importer-project")
        exporter_project = await create_project(
            session=session, owner=user, name="exporter-project"
        )
        local_fleet = await create_fleet(session=session, project=project, name="same-fleet")
        exported_fleet = await create_fleet(
            session=session, project=exporter_project, name="same-fleet"
        )
        unrelated_fleet = await create_fleet(
            session=session, project=project, name="unrelated-fleet"
        )
        await create_instance(
            session=session,
            project=project,
            fleet=local_fleet,
            instance_num=1,
        )
        await create_instance(
            session=session,
            project=exporter_project,
            fleet=exported_fleet,
            instance_num=1,
        )
        await create_instance(
            session=session,
            project=project,
            fleet=unrelated_fleet,
            instance_num=1,
        )
        await create_export(
            session=session,
            exporter_project=exporter_project,
            importer_projects=[project],
            exported_fleets=[exported_fleet],
        )
        run_spec = get_run_spec(
            repo_id="test-repo",
            configuration=TaskConfiguration(image="debian", commands=["echo"]),
            profile=Profile(instances=[FleetInstanceSelector(fleet=selector, instance=1)]),
        )
        fleet_filters, instance_filters = await get_run_candidate_fleet_models_filters(
            session=session,
            project=project,
            run_model=None,
            run_spec=run_spec,
        )

        (
            fleets_with_instances,
            fleets_without_instances,
        ) = await select_run_candidate_fleet_models_with_filters(
            session=session,
            fleet_filters=fleet_filters,
            instance_filters=instance_filters,
            lock_instances=False,
        )

        assert [fleet.project.name for fleet in fleets_with_instances] == [
            expected_fleet_project_name
        ]
        assert fleets_without_instances == []


class TestFindOptimalFleetWithOffers:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_skips_backend_offers_when_instances_specified(
        self, test_db, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user = await create_user(session=session)
        project = await create_project(session=session, owner=user)
        repo = await create_repo(session=session, project_id=project.id)
        fleet = await create_fleet(session=session, project=project)
        run_spec = get_run_spec(
            repo_id=repo.name,
            configuration=TaskConfiguration(image="debian", commands=["echo"]),
            profile=Profile(instances=[InstanceNameSelector(name="missing-instance")]),
        )
        jobs = await get_jobs_from_run_spec(run_spec=run_spec, secrets={}, replica_num=0)
        get_backend_offers_in_fleet_mock = AsyncMock()
        monkeypatch.setattr(
            "dstack._internal.server.services.runs.plan._get_backend_offers_in_fleet",
            get_backend_offers_in_fleet_mock,
        )

        fleet_model, instance_offers, backend_offers = await find_optimal_fleet_with_offers(
            project=project,
            fleet_models=[fleet],
            run_model=None,
            run_spec=run_spec,
            job=jobs[0],
            master_job_provisioning_data=None,
            volumes=None,
            exclude_not_available=False,
        )

        assert fleet_model == fleet
        assert instance_offers == []
        assert backend_offers == []
        get_backend_offers_in_fleet_mock.assert_not_awaited()


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
