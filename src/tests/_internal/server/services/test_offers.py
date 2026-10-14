from unittest.mock import Mock, patch

import pytest

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
)
from dstack._internal.core.models.placement import PlacementGroup
from dstack._internal.core.models.profiles import Profile
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.runs import Requirements
from dstack._internal.core.models.volumes import DaytonaVolumeConfiguration
from dstack._internal.server.services.offers import get_offers_by_requirements
from dstack._internal.server.testing.common import (
    ComputeMockSpec,
    get_instance_offer_with_availability,
    get_kubernetes_volume_configuration,
    get_placement_group_configuration,
    get_volume,
    get_volume_configuration,
)


class TestGetOffersByRequirements:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("exclude_not_available", [False, True])
    async def test_stops_at_max_offers(self, exclude_not_available):
        offer = get_instance_offer_with_availability()
        backend = Mock(TYPE=BackendType.AWS)

        def iterate_offers():
            yield offer
            raise AssertionError("Planning consumed offers beyond max_offers")

        backend.compute.return_value.get_offers.return_value = iterate_offers()
        with patch(
            "dstack._internal.server.services.backends.get_project_backends",
            return_value=[backend],
        ):
            result = await get_offers_by_requirements(
                project=Mock(),
                profile=Profile(),
                requirements=Requirements(resources=ResourcesSpec()),
                max_offers=1,
                exclude_not_available=exclude_not_available,
            )
        assert result.offers == [(backend, offer)]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("availabilities", "no_quota", "no_balance"),
        [
            ([], False, False),
            ([InstanceAvailability.NO_QUOTA], True, False),
            ([InstanceAvailability.NO_BALANCE], False, True),
            ([InstanceAvailability.NO_QUOTA, InstanceAvailability.NOT_AVAILABLE], False, False),
            ([InstanceAvailability.NO_BALANCE, InstanceAvailability.NOT_AVAILABLE], False, False),
            ([InstanceAvailability.NO_QUOTA, InstanceAvailability.NO_BALANCE], False, False),
            ([InstanceAvailability.AVAILABLE, InstanceAvailability.NO_QUOTA], False, False),
            ([InstanceAvailability.AVAILABLE, InstanceAvailability.NO_BALANCE], False, False),
        ],
    )
    async def test_collects_unavailable_offers_without_returning_them(
        self, availabilities, no_quota, no_balance
    ):
        backend = Mock(TYPE=BackendType.DSTACK)
        offers = [get_instance_offer_with_availability(availability=a) for a in availabilities]
        backend.compute.return_value.get_offers.return_value = iter(offers)
        with patch(
            "dstack._internal.server.services.backends.get_project_backends",
            return_value=[backend],
        ):
            result = await get_offers_by_requirements(
                project=Mock(),
                profile=Profile(),
                requirements=Requirements(resources=ResourcesSpec()),
                exclude_not_available=True,
            )
        assert result.offers == [
            (backend, offer) for offer in offers if offer.availability.is_available()
        ]
        assert (result.unavailable_reason == InstanceAvailability.NO_QUOTA) == no_quota
        assert (result.unavailable_reason == InstanceAvailability.NO_BALANCE) == no_balance
        backend.compute.return_value.get_offers.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("profile", "ignored_offer", "blocks", "supported_backends"),
        [
            (
                Profile(backends=[BackendType.AWS]),
                get_instance_offer_with_availability(backend=BackendType.GCP),
                1,
                None,
            ),
            (
                Profile(regions=["eu-west"]),
                get_instance_offer_with_availability(region="us-east"),
                1,
                None,
            ),
            (
                Profile(instance_types=["instance"]),
                get_instance_offer_with_availability(instance_type="other"),
                1,
                None,
            ),
            (
                Profile(availability_zones=["AZ1"]),
                get_instance_offer_with_availability(availability_zones=["az2"]),
                1,
                None,
            ),
            (
                Profile(availability_zones=["az1"]),
                get_instance_offer_with_availability(availability_zones=None),
                1,
                None,
            ),
            (Profile(), get_instance_offer_with_availability(cpu_count=3), 2, None),
            (
                Profile(),
                get_instance_offer_with_availability(backend=BackendType.KUBERNETES),
                1,
                [BackendType.AWS],
            ),
        ],
    )
    async def test_ignores_unavailable_offers_that_do_not_match(
        self,
        profile: Profile,
        ignored_offer: InstanceOfferWithAvailability,
        blocks,
        supported_backends,
    ):
        quota_offer = get_instance_offer_with_availability(
            availability=InstanceAvailability.NO_QUOTA, availability_zones=["az1"]
        )
        ignored_offer = ignored_offer.model_copy(
            update={"availability": InstanceAvailability.NOT_AVAILABLE}
        )
        backend = Mock(TYPE=BackendType.DSTACK)
        backend.compute.return_value.get_offers.return_value = [quota_offer, ignored_offer]
        with patch(
            "dstack._internal.server.services.backends.get_project_backends",
            return_value=[backend],
        ):
            result = await get_offers_by_requirements(
                project=Mock(),
                profile=profile,
                requirements=Requirements(resources=ResourcesSpec()),
                exclude_not_available=True,
                blocks=blocks,
                supported_backend_types=supported_backends,
            )
        assert result.offers == []
        assert result.unavailable_reason == InstanceAvailability.NO_QUOTA

    @pytest.mark.asyncio
    async def test_does_not_copy_unavailable_offers_for_az_or_blocks(self):
        offer = get_instance_offer_with_availability(
            availability=InstanceAvailability.NO_QUOTA,
            availability_zones=["AZ1", "az2"],
            cpu_count=128,
            gpu_count=8,
        )
        backend = Mock(TYPE=BackendType.DSTACK)
        backend.compute.return_value.get_offers.return_value = (offer for _ in range(1000))
        with (
            patch(
                "dstack._internal.server.services.backends.get_project_backends",
                return_value=[backend],
            ),
            patch.object(InstanceOfferWithAvailability, "model_copy", side_effect=AssertionError),
        ):
            result = await get_offers_by_requirements(
                project=Mock(),
                profile=Profile(availability_zones=["az1"]),
                requirements=Requirements(resources=ResourcesSpec()),
                blocks="auto",
                exclude_not_available=True,
            )
        assert result.offers == []
        assert result.unavailable_reason == InstanceAvailability.NO_QUOTA
        assert offer.availability_zones == ["AZ1", "az2"]
        assert offer.total_blocks == 1

    @pytest.mark.asyncio
    async def test_only_collects_unavailable_offers_in_the_volume_location(self):
        backend = Mock(TYPE=BackendType.DSTACK)
        backend.compute.return_value.get_offers.return_value = [
            get_instance_offer_with_availability(availability=InstanceAvailability.NO_QUOTA),
            get_instance_offer_with_availability(
                availability=InstanceAvailability.NOT_AVAILABLE, region="other-region"
            ),
            get_instance_offer_with_availability(
                availability=InstanceAvailability.NOT_AVAILABLE, backend=BackendType.GCP
            ),
        ]
        with patch(
            "dstack._internal.server.services.backends.get_project_backends",
            return_value=[backend],
        ):
            result = await get_offers_by_requirements(
                project=Mock(),
                profile=Profile(),
                requirements=Requirements(resources=ResourcesSpec()),
                exclude_not_available=True,
                volumes=[[get_volume(configuration=get_volume_configuration(region="eu-west"))]],
            )
        assert result.offers == []
        assert result.unavailable_reason == InstanceAvailability.NO_QUOTA

    @pytest.mark.asyncio
    async def test_only_collects_unavailable_offers_suitable_for_the_placement_group(self):
        backend = Mock(TYPE=BackendType.DSTACK)
        compute = Mock(spec=ComputeMockSpec)
        backend.compute.return_value = compute
        compute.is_suitable_placement_group.side_effect = (
            lambda pg, offer: offer.region == pg.configuration.region
        )
        compute.get_offers.return_value = [
            get_instance_offer_with_availability(availability=InstanceAvailability.NO_QUOTA),
            get_instance_offer_with_availability(
                availability=InstanceAvailability.NOT_AVAILABLE, region="other-region"
            ),
        ]
        with patch(
            "dstack._internal.server.services.backends.get_project_backends",
            return_value=[backend],
        ):
            result = await get_offers_by_requirements(
                project=Mock(),
                profile=Profile(),
                requirements=Requirements(resources=ResourcesSpec()),
                exclude_not_available=True,
                placement_group=PlacementGroup(
                    name="placement-group",
                    project_name="test_project",
                    configuration=get_placement_group_configuration(region="eu-west"),
                ),
            )
        assert result.offers == []
        assert result.unavailable_reason == InstanceAvailability.NO_QUOTA

    @pytest.mark.asyncio
    @pytest.mark.parametrize("feature", ["multinode", "privileged", "instance_mounts"])
    async def test_only_collects_unavailable_offers_with_required_features(self, feature):
        backend = Mock(TYPE=BackendType.DSTACK)
        backend.compute.return_value.get_offers.return_value = [
            get_instance_offer_with_availability(availability=InstanceAvailability.NO_QUOTA),
            get_instance_offer_with_availability(
                backend=BackendType.DAYTONA, availability=InstanceAvailability.NOT_AVAILABLE
            ),
        ]
        with patch(
            "dstack._internal.server.services.backends.get_project_backends",
            return_value=[backend],
        ):
            result = await get_offers_by_requirements(
                project=Mock(),
                profile=Profile(),
                requirements=Requirements(resources=ResourcesSpec()),
                exclude_not_available=True,
                **{feature: True},
            )
        assert result.offers == []
        assert result.unavailable_reason == InstanceAvailability.NO_QUOTA

    @pytest.mark.asyncio
    async def test_preserves_available_offer_order_when_a_backend_is_not_sorted_by_price(self):
        vastai = Mock(TYPE=BackendType.VASTAI)
        first = get_instance_offer_with_availability(backend=BackendType.VASTAI, price=1)
        blocked = get_instance_offer_with_availability(
            backend=BackendType.VASTAI, price=100, availability=InstanceAvailability.NO_QUOTA
        )
        second = get_instance_offer_with_availability(backend=BackendType.VASTAI, price=2)
        vastai.compute.return_value.get_offers.return_value = [first, blocked, second]
        aws = Mock(TYPE=BackendType.AWS)
        third = get_instance_offer_with_availability(price=3)
        aws.compute.return_value.get_offers.return_value = [third]
        with patch(
            "dstack._internal.server.services.backends.get_project_backends",
            return_value=[vastai, aws],
        ):
            result = await get_offers_by_requirements(
                project=Mock(),
                profile=Profile(),
                requirements=Requirements(resources=ResourcesSpec()),
                exclude_not_available=True,
            )
        assert result.offers == [(vastai, first), (vastai, second), (aws, third)]

    @pytest.mark.asyncio
    async def test_returns_all_offers(self):
        profile = Profile(name="test")
        requirements = Requirements(resources=ResourcesSpec())
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            aws_backend_mock = Mock()
            aws_backend_mock.TYPE = BackendType.AWS
            aws_offer = get_instance_offer_with_availability(backend=BackendType.AWS)
            aws_backend_mock.compute.return_value.get_offers.return_value = [aws_offer]
            runpod_backend_mock = Mock()
            runpod_backend_mock.TYPE = BackendType.RUNPOD
            runpod_offer = get_instance_offer_with_availability(backend=BackendType.RUNPOD)
            runpod_backend_mock.compute.return_value.get_offers.return_value = [runpod_offer]
            m.return_value = [aws_backend_mock, runpod_backend_mock]
            res = await get_offers_by_requirements(
                project=Mock(),
                profile=profile,
                requirements=requirements,
            )
            m.assert_awaited_once()
            assert res.offers == [
                (aws_backend_mock, aws_offer),
                (runpod_backend_mock, runpod_offer),
            ]

    @pytest.mark.asyncio
    async def test_returns_multinode_offers(self):
        profile = Profile(name="test")
        requirements = Requirements(resources=ResourcesSpec())
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            aws_backend_mock = Mock()
            aws_backend_mock.TYPE = BackendType.AWS
            aws_offer = get_instance_offer_with_availability(backend=BackendType.AWS)
            aws_backend_mock.compute.return_value.get_offers.return_value = [aws_offer]
            vastai_backend_mock = Mock()
            vastai_backend_mock.TYPE = BackendType.VASTAI
            vastai_offer = get_instance_offer_with_availability(backend=BackendType.VASTAI)
            vastai_backend_mock.compute.return_value.get_offers.return_value = [vastai_offer]
            m.return_value = [aws_backend_mock, vastai_backend_mock]
            res = await get_offers_by_requirements(
                project=Mock(),
                profile=profile,
                requirements=requirements,
                multinode=True,
            )
            m.assert_awaited_once()
            assert res.offers == [(aws_backend_mock, aws_offer)]

    @pytest.mark.asyncio
    async def test_returns_volume_offers(self):
        profile = Profile(name="test")
        requirements = Requirements(resources=ResourcesSpec())
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            aws_backend_mock = Mock()
            aws_backend_mock.TYPE = BackendType.AWS
            aws_offer = get_instance_offer_with_availability(backend=BackendType.AWS)
            aws_backend_mock.compute.return_value.get_offers.return_value = [aws_offer]
            runpod_backend_mock = Mock()
            runpod_backend_mock.TYPE = BackendType.RUNPOD
            runpod_offer1 = get_instance_offer_with_availability(
                backend=BackendType.RUNPOD, region="eu"
            )
            runpod_offer2 = get_instance_offer_with_availability(
                backend=BackendType.RUNPOD, region="us"
            )
            runpod_backend_mock.compute.return_value.get_offers.return_value = [
                runpod_offer1,
                runpod_offer2,
            ]
            m.return_value = [aws_backend_mock, runpod_backend_mock]
            res = await get_offers_by_requirements(
                project=Mock(),
                profile=profile,
                requirements=requirements,
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
            m.assert_awaited_once()
            assert res.offers == [(runpod_backend_mock, runpod_offer2)]

    @pytest.mark.asyncio
    async def test_global_volume_matches_cpu_and_gpu_regions(self):
        daytona_backend = Mock(TYPE=BackendType.DAYTONA)
        cpu_offer = get_instance_offer_with_availability(backend=BackendType.DAYTONA, region="us")
        gpu_offer = get_instance_offer_with_availability(
            backend=BackendType.DAYTONA, region="earth", gpu_count=1
        )
        daytona_backend.compute.return_value.get_offers.return_value = [cpu_offer, gpu_offer]
        aws_backend = Mock(TYPE=BackendType.AWS)
        aws_offer = get_instance_offer_with_availability(backend=BackendType.AWS, region="us")
        aws_backend.compute.return_value.get_offers.return_value = [aws_offer]

        with patch(
            "dstack._internal.server.services.backends.get_project_backends",
            return_value=[daytona_backend, aws_backend],
        ):
            offers = await get_offers_by_requirements(
                project=Mock(),
                profile=Profile(),
                requirements=Requirements(resources=ResourcesSpec()),
                volumes=[[get_volume(configuration=DaytonaVolumeConfiguration())]],
            )

        assert offers.offers == [(daytona_backend, cpu_offer), (daytona_backend, gpu_offer)]

    @pytest.mark.asyncio
    async def test_returns_volume_offers_without_region(self):
        profile = Profile(name="test")
        requirements = Requirements(resources=ResourcesSpec())
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            aws_backend_mock = Mock()
            aws_backend_mock.TYPE = BackendType.AWS
            aws_offer = get_instance_offer_with_availability(backend=BackendType.AWS)
            aws_backend_mock.compute.return_value.get_offers.return_value = [aws_offer]
            kubernetes_backend_mock = Mock()
            kubernetes_backend_mock.TYPE = BackendType.KUBERNETES
            kubernetes_offer = get_instance_offer_with_availability(
                backend=BackendType.KUBERNETES,
                region="",
                availability_zones=None,
            )
            kubernetes_backend_mock.compute.return_value.get_offers.return_value = [
                kubernetes_offer,
                get_instance_offer_with_availability(
                    backend=BackendType.KUBERNETES, region="other-cluster"
                ),
            ]
            m.return_value = [aws_backend_mock, kubernetes_backend_mock]
            res = await get_offers_by_requirements(
                project=Mock(),
                profile=profile,
                requirements=requirements,
                volumes=[[get_volume(configuration=get_kubernetes_volume_configuration())]],
            )
            m.assert_awaited_once()
            assert res.offers == [(kubernetes_backend_mock, kubernetes_offer)]

    @pytest.mark.asyncio
    async def test_returns_az_offers(self):
        profile = Profile(name="test", availability_zones=["az1", "az3"])
        requirements = Requirements(resources=ResourcesSpec())
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            aws_backend_mock = Mock()
            aws_backend_mock.TYPE = BackendType.AWS
            aws_offer1 = get_instance_offer_with_availability(
                backend=BackendType.AWS, availability_zones=["az1"]
            )
            aws_offer2 = get_instance_offer_with_availability(
                backend=BackendType.AWS, availability_zones=["az2"]
            )
            aws_offer3 = get_instance_offer_with_availability(
                backend=BackendType.AWS, availability_zones=["az2", "az3"]
            )
            expected_aws_offer3 = aws_offer3.model_copy()
            expected_aws_offer3.availability_zones = ["az3"]
            aws_offer4 = get_instance_offer_with_availability(
                backend=BackendType.AWS, availability_zones=None
            )
            aws_backend_mock.compute.return_value.get_offers.return_value = [
                aws_offer1,
                aws_offer2,
                aws_offer3,
                aws_offer4,
            ]
            m.return_value = [aws_backend_mock]
            res = await get_offers_by_requirements(
                project=Mock(),
                profile=profile,
                requirements=requirements,
            )
            m.assert_awaited_once()
            assert res.offers == [
                (aws_backend_mock, aws_offer1),
                (aws_backend_mock, expected_aws_offer3),
            ]

    @pytest.mark.asyncio
    async def test_returns_az_offers_ignoring_case(self):
        profile = Profile(name="test", availability_zones=["AZ1"])
        requirements = Requirements(resources=ResourcesSpec())
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            aws_backend_mock = Mock()
            aws_backend_mock.TYPE = BackendType.AWS
            aws_offer = get_instance_offer_with_availability(
                backend=BackendType.AWS, availability_zones=["az1", "az2"]
            )
            # The offer keeps the zone spelling reported by the backend.
            expected_aws_offer = aws_offer.model_copy()
            expected_aws_offer.availability_zones = ["az1"]
            aws_backend_mock.compute.return_value.get_offers.return_value = [aws_offer]
            m.return_value = [aws_backend_mock]
            res = await get_offers_by_requirements(
                project=Mock(),
                profile=profile,
                requirements=requirements,
            )
            assert res.offers == [(aws_backend_mock, expected_aws_offer)]

    @pytest.mark.asyncio
    async def test_returns_no_offers_for_multinode_instance_mounts_and_non_multinode_backend(self):
        # Regression test for https://github.com/dstackai/dstack/issues/2211
        profile = Profile(name="test", backends=[BackendType.RUNPOD])
        requirements = Requirements(resources=ResourcesSpec())
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            aws_backend_mock = Mock()
            aws_backend_mock.TYPE = BackendType.AWS
            aws_offer = get_instance_offer_with_availability(backend=BackendType.AWS)
            aws_backend_mock.compute.return_value.get_offers.return_value = [aws_offer]
            runpod_backend_mock = Mock()
            runpod_backend_mock.TYPE = BackendType.RUNPOD
            runpod_offer = get_instance_offer_with_availability(backend=BackendType.RUNPOD)
            runpod_backend_mock.compute.return_value.get_offers.return_value = [runpod_offer]
            m.return_value = [aws_backend_mock, runpod_backend_mock]
            res = await get_offers_by_requirements(
                project=Mock(),
                profile=profile,
                requirements=requirements,
                multinode=True,
                instance_mounts=True,
            )
            m.assert_awaited_once()
            assert res.offers == []
