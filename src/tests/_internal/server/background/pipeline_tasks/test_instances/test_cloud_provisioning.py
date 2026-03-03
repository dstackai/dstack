import datetime as dt
from collections import defaultdict
from typing import Optional
from unittest.mock import Mock, patch

import gpuhunt
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import NoCapacityError, ProvisioningError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.fleets import FleetNodesSpec, InstanceGroupPlacement
from dstack._internal.core.models.instances import (
    Gpu,
    InstanceAvailability,
    InstanceOffer,
    InstanceOfferWithAvailability,
    InstanceStatus,
    InstanceTerminationReason,
    InstanceType,
    Resources,
)
from dstack._internal.core.models.placement import PlacementGroup, PlacementGroupProvisioningData
from dstack._internal.core.models.runs import JobProvisioningData
from dstack._internal.server.background.pipeline_tasks.instances import InstanceWorker
from dstack._internal.server.models import PlacementGroupModel
from dstack._internal.server.testing.common import (
    ComputeMockSpec,
    create_fleet,
    create_instance,
    create_project,
    get_fleet_configuration,
    get_fleet_spec,
    get_instance_offer_with_availability,
    get_job_provisioning_data,
    get_placement_group_provisioning_data,
)
from tests._internal.server.background.pipeline_tasks.test_instances.helpers import (
    process_instance,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestCloudProvisioning:
    @pytest.mark.parametrize(
        ["cpus", "gpus", "requested_blocks", "expected_blocks"],
        [
            pytest.param(32, 8, 1, 1, id="gpu-instance-no-blocks"),
            pytest.param(32, 8, 2, 2, id="gpu-instance-four-gpu-per-block"),
            pytest.param(32, 8, 4, 4, id="gpu-instance-two-gpus-per-block"),
            pytest.param(32, 8, None, 8, id="gpu-instance-auto-max-gpu"),
            pytest.param(4, 8, None, 4, id="gpu-instance-auto-max-cpu"),
            pytest.param(8, 8, None, 8, id="gpu-instance-auto-max-cpu-and-gpu"),
            pytest.param(32, 0, 1, 1, id="cpu-instance-no-blocks"),
            pytest.param(32, 0, 2, 2, id="cpu-instance-four-cpu-per-block"),
            pytest.param(32, 0, 4, 4, id="cpu-instance-two-cpus-per-block"),
            pytest.param(32, 0, None, 32, id="cpu-instance-auto-max-cpu"),
        ],
    )
    async def test_creates_instance(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
        cpus: int,
        gpus: int,
        requested_blocks: Optional[int],
        expected_blocks: int,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PENDING,
            total_blocks=requested_blocks,
            busy_blocks=0,
        )
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock = Mock()
            m.return_value = [backend_mock]
            backend_mock.TYPE = BackendType.AWS
            gpu = Gpu(name="T4", memory_mib=16384, vendor=gpuhunt.AcceleratorVendor.NVIDIA)
            offer = InstanceOfferWithAvailability(
                backend=BackendType.AWS,
                instance=InstanceType(
                    name="instance",
                    resources=Resources(
                        cpus=cpus,
                        memory_mib=131072,
                        spot=False,
                        gpus=[gpu] * gpus,
                    ),
                ),
                region="us",
                price=1.0,
                availability=InstanceAvailability.AVAILABLE,
                total_blocks=expected_blocks,
            )
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            backend_mock.compute.return_value.get_offers.return_value = [offer]
            backend_mock.compute.return_value.create_instance.return_value = JobProvisioningData(
                backend=offer.backend,
                instance_type=offer.instance,
                instance_id="instance_id",
                hostname="1.1.1.1",
                internal_ip=None,
                region=offer.region,
                price=offer.price,
                username="ubuntu",
                ssh_port=22,
                ssh_proxy=None,
                dockerized=True,
                backend_data=None,
            )

            await process_instance(session, worker, instance)

        await session.refresh(instance)
        assert instance.status == InstanceStatus.PROVISIONING
        assert instance.total_blocks == expected_blocks
        assert instance.busy_blocks == 0

    @pytest.mark.parametrize("err", [RuntimeError("Unexpected"), ProvisioningError("Expected")])
    async def test_tries_second_offer_if_first_fails(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
        err: Exception,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PENDING,
        )
        aws_mock = Mock()
        aws_mock.TYPE = BackendType.AWS
        offer = get_instance_offer_with_availability(backend=BackendType.AWS, price=1.0)
        aws_mock.compute.return_value = Mock(spec=ComputeMockSpec)
        aws_mock.compute.return_value.get_offers.return_value = [offer]
        aws_mock.compute.return_value.create_instance.side_effect = err
        gcp_mock = Mock()
        gcp_mock.TYPE = BackendType.GCP
        offer = get_instance_offer_with_availability(backend=BackendType.GCP, price=2.0)
        gcp_mock.compute.return_value = Mock(spec=ComputeMockSpec)
        gcp_mock.compute.return_value.get_offers.return_value = [offer]
        gcp_mock.compute.return_value.create_instance.return_value = get_job_provisioning_data(
            backend=offer.backend,
            region=offer.region,
            price=offer.price,
        )
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            m.return_value = [aws_mock, gcp_mock]
            await process_instance(session, worker, instance)

        await session.refresh(instance)
        assert instance.status == InstanceStatus.PROVISIONING
        aws_mock.compute.return_value.create_instance.assert_called_once()
        assert instance.backend == BackendType.GCP

    @pytest.mark.parametrize("err", [RuntimeError("Unexpected"), ProvisioningError("Expected")])
    async def test_fails_if_all_offers_fail(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
        err: Exception,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PENDING,
        )
        aws_mock = Mock()
        aws_mock.TYPE = BackendType.AWS
        offer = get_instance_offer_with_availability(backend=BackendType.AWS, price=1.0)
        aws_mock.compute.return_value = Mock(spec=ComputeMockSpec)
        aws_mock.compute.return_value.get_offers.return_value = [offer]
        aws_mock.compute.return_value.create_instance.side_effect = err
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            m.return_value = [aws_mock]
            await process_instance(session, worker, instance)

        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATED
        assert instance.termination_reason == InstanceTerminationReason.NO_OFFERS

    async def test_fails_if_no_offers(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
    ):
        project = await create_project(session=session)
        instance = await create_instance(
            session=session,
            project=project,
            status=InstanceStatus.PENDING,
        )
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            m.return_value = []
            await process_instance(session, worker, instance)

        await session.refresh(instance)
        assert instance.status == InstanceStatus.TERMINATED
        assert instance.termination_reason == InstanceTerminationReason.NO_OFFERS

    @pytest.mark.parametrize(
        ("placement", "expected_termination_reasons"),
        [
            pytest.param(
                InstanceGroupPlacement.CLUSTER,
                {
                    InstanceTerminationReason.NO_OFFERS: 1,
                    InstanceTerminationReason.MASTER_FAILED: 3,
                },
                id="cluster",
            ),
            pytest.param(
                None,
                {InstanceTerminationReason.NO_OFFERS: 4},
                id="non-cluster",
            ),
        ],
    )
    async def test_terminates_cluster_instances_if_master_not_created(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
        placement: Optional[InstanceGroupPlacement],
        expected_termination_reasons: dict[str, int],
    ):
        project = await create_project(session=session)
        fleet = await create_fleet(
            session,
            project,
            spec=get_fleet_spec(
                conf=get_fleet_configuration(
                    placement=placement, nodes=FleetNodesSpec(min=4, target=4, max=4)
                )
            ),
        )
        instances = [
            await create_instance(
                session=session,
                project=project,
                fleet=fleet,
                status=InstanceStatus.PENDING,
                offer=None,
                job_provisioning_data=None,
                instance_num=index,
                created_at=dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=index),
            )
            for index in range(4)
        ]
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            m.return_value = []
            for instance in sorted(instances, key=lambda i: (i.instance_num, i.created_at)):
                await process_instance(session, worker, instance)

        termination_reasons = defaultdict(int)
        for instance in instances:
            await session.refresh(instance)
            assert instance.status == InstanceStatus.TERMINATED
            termination_reasons[instance.termination_reason] += 1
        assert termination_reasons == expected_termination_reasons

    @pytest.mark.parametrize(
        ("placement", "should_create"),
        [
            pytest.param(InstanceGroupPlacement.CLUSTER, True, id="placement-cluster"),
            pytest.param(None, False, id="no-placement"),
        ],
    )
    async def test_create_placement_group_if_placement_cluster(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
        placement: Optional[InstanceGroupPlacement],
        should_create: bool,
    ) -> None:
        project = await create_project(session=session)
        fleet = await create_fleet(
            session,
            project,
            spec=get_fleet_spec(
                conf=get_fleet_configuration(
                    placement=placement, nodes=FleetNodesSpec(min=1, target=1, max=1)
                )
            ),
        )
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.PENDING,
            offer=None,
            job_provisioning_data=None,
        )
        backend_mock = Mock()
        backend_mock.TYPE = BackendType.AWS
        backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
        backend_mock.compute.return_value.get_offers.return_value = [
            get_instance_offer_with_availability()
        ]
        backend_mock.compute.return_value.create_instance.return_value = (
            get_job_provisioning_data()
        )
        backend_mock.compute.return_value.create_placement_group.return_value = (
            get_placement_group_provisioning_data()
        )
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            m.return_value = [backend_mock]
            await process_instance(session, worker, instance)

        await session.refresh(instance)
        assert instance.status == InstanceStatus.PROVISIONING
        placement_groups = (await session.execute(select(PlacementGroupModel))).scalars().all()
        if should_create:
            assert backend_mock.compute.return_value.create_placement_group.call_count == 1
            assert len(placement_groups) == 1
        else:
            assert backend_mock.compute.return_value.create_placement_group.call_count == 0
            assert len(placement_groups) == 0

    @pytest.mark.parametrize("can_reuse", [True, False])
    async def test_reuses_placement_group_between_offers_if_the_group_is_suitable(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
        can_reuse: bool,
    ) -> None:
        project = await create_project(session=session)
        fleet = await create_fleet(
            session,
            project,
            spec=get_fleet_spec(
                conf=get_fleet_configuration(
                    placement=InstanceGroupPlacement.CLUSTER,
                    nodes=FleetNodesSpec(min=1, target=1, max=1),
                )
            ),
        )
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.PENDING,
            offer=None,
            job_provisioning_data=None,
        )
        backend_mock = Mock()
        backend_mock.TYPE = BackendType.AWS
        backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
        backend_mock.compute.return_value.get_offers.return_value = [
            get_instance_offer_with_availability(instance_type="bad-offer-1"),
            get_instance_offer_with_availability(instance_type="bad-offer-2"),
            get_instance_offer_with_availability(instance_type="good-offer"),
        ]

        def create_instance_method(
            instance_offer: InstanceOfferWithAvailability, *args, **kwargs
        ) -> JobProvisioningData:
            if instance_offer.instance.name == "good-offer":
                return get_job_provisioning_data()
            raise NoCapacityError()

        backend_mock.compute.return_value.create_instance = create_instance_method
        backend_mock.compute.return_value.create_placement_group.return_value = (
            get_placement_group_provisioning_data()
        )
        backend_mock.compute.return_value.is_suitable_placement_group.return_value = can_reuse
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            m.return_value = [backend_mock]
            await process_instance(session, worker, instance)

        await session.refresh(instance)
        assert instance.status == InstanceStatus.PROVISIONING
        placement_groups = (await session.execute(select(PlacementGroupModel))).scalars().all()
        if can_reuse:
            assert backend_mock.compute.return_value.create_placement_group.call_count == 1
            assert len(placement_groups) == 1
        else:
            assert backend_mock.compute.return_value.create_placement_group.call_count == 3
            assert len(placement_groups) == 3
            to_be_deleted_count = sum(pg.fleet_deleted for pg in placement_groups)
            assert to_be_deleted_count == 2

    @pytest.mark.parametrize("err", [NoCapacityError(), RuntimeError()])
    async def test_handles_create_placement_group_errors(
        self,
        test_db,
        session: AsyncSession,
        worker: InstanceWorker,
        err: Exception,
    ) -> None:
        project = await create_project(session=session)
        fleet = await create_fleet(
            session,
            project,
            spec=get_fleet_spec(
                conf=get_fleet_configuration(
                    placement=InstanceGroupPlacement.CLUSTER,
                    nodes=FleetNodesSpec(min=1, target=1, max=1),
                )
            ),
        )
        instance = await create_instance(
            session=session,
            project=project,
            fleet=fleet,
            status=InstanceStatus.PENDING,
            offer=None,
            job_provisioning_data=None,
        )
        backend_mock = Mock()
        backend_mock.TYPE = BackendType.AWS
        backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
        backend_mock.compute.return_value.get_offers.return_value = [
            get_instance_offer_with_availability(instance_type="bad-offer"),
            get_instance_offer_with_availability(instance_type="good-offer"),
        ]
        backend_mock.compute.return_value.create_instance.return_value = (
            get_job_provisioning_data()
        )

        def create_placement_group_method(
            placement_group: PlacementGroup, master_instance_offer: InstanceOffer
        ) -> PlacementGroupProvisioningData:
            if master_instance_offer.instance.name == "good-offer":
                return get_placement_group_provisioning_data()
            raise err

        backend_mock.compute.return_value.create_placement_group = create_placement_group_method
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            m.return_value = [backend_mock]
            await process_instance(session, worker, instance)

        await session.refresh(instance)
        assert instance.status == InstanceStatus.PROVISIONING
        assert instance.offer
        assert "good-offer" in instance.offer
        assert "bad-offer" not in instance.offer
        placement_groups = (await session.execute(select(PlacementGroupModel))).scalars().all()
        assert len(placement_groups) == 1
