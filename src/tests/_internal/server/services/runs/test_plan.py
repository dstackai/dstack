import copy
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.configurations import TaskConfiguration
from dstack._internal.core.models.fleets import FleetNodesSpec, InstanceGroupPlacement
from dstack._internal.core.models.instances import InstanceAvailability
from dstack._internal.server.services.jobs import get_jobs_from_run_spec
from dstack._internal.server.services.runs.plan import (
    _freeze_offer_identity_value,
    _get_backend_offer_identity,
    _get_backend_offers_in_fleet,
)
from dstack._internal.server.testing.common import (
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
