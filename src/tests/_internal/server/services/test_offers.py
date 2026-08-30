from unittest.mock import Mock, patch

import pytest

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.profiles import Profile
from dstack._internal.core.models.resources import CPUSpec, Memory, Range, ResourcesSpec
from dstack._internal.core.models.runs import Requirements
from dstack._internal.server.services.offers import get_offers_by_requirements
from dstack._internal.server.testing.common import (
    ComputeMockSpec,
    get_instance_offer_with_availability,
    get_kubernetes_volume_configuration,
    get_volume,
    get_volume_configuration,
)


class TestGetOffersByRequirements:
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
            assert res == [(aws_backend_mock, aws_offer), (runpod_backend_mock, runpod_offer)]

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
            assert res == [(aws_backend_mock, aws_offer)]

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
            assert res == [(runpod_backend_mock, runpod_offer2)]

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
                kubernetes_offer
            ]
            m.return_value = [aws_backend_mock, kubernetes_backend_mock]
            res = await get_offers_by_requirements(
                project=Mock(),
                profile=profile,
                requirements=requirements,
                volumes=[[get_volume(configuration=get_kubernetes_volume_configuration())]],
            )
            m.assert_awaited_once()
            assert res == [(kubernetes_backend_mock, kubernetes_offer)]

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
            assert res == [(aws_backend_mock, aws_offer1), (aws_backend_mock, expected_aws_offer3)]

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
            assert res == [(aws_backend_mock, expected_aws_offer)]

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
            assert res == []

    @pytest.mark.asyncio
    async def test_filters_shared_offers_before_max_offers(self):
        profile = Profile(name="test")
        requirements = Requirements(
            resources=ResourcesSpec(
                cpu=CPUSpec.parse("4..8"),
                memory=Range[Memory](min=Memory.parse("8GB"), max=Memory.parse("32GB")),
                gpu=None,
            )
        )
        shared_offer_requirements = Requirements(
            resources=ResourcesSpec(
                cpu=CPUSpec.parse("2"),
                memory=Range[Memory](min=Memory.parse("3GB"), max=None),
                gpu=None,
            )
        )
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock = Mock()
            backend_mock.TYPE = BackendType.SEEWEB
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            nonmatching_offer = get_instance_offer_with_availability(
                backend=BackendType.SEEWEB,
                instance_type="nonmatching",
                cpu_count=6,
                memory_gib=8,
            )
            matching_offer = get_instance_offer_with_availability(
                backend=BackendType.SEEWEB,
                instance_type="matching",
                cpu_count=4,
                memory_gib=8,
            )
            backend_mock.compute.return_value.get_offers.return_value = [
                nonmatching_offer,
                matching_offer,
            ]
            m.return_value = [backend_mock]
            res = await get_offers_by_requirements(
                project=Mock(),
                profile=profile,
                requirements=requirements,
                shared_offer_requirements=shared_offer_requirements,
                blocks="auto",
                max_offers=1,
            )

            assert [
                (backend, offer.instance.name, offer.blocks, offer.total_blocks)
                for backend, offer in res
            ] == [(backend_mock, "matching", 2, 4)]

    @pytest.mark.asyncio
    async def test_filters_non_create_dstack_wrapper_offers_before_max_offers(self):
        profile = Profile(name="test")
        requirements = Requirements(
            resources=ResourcesSpec(
                cpu=CPUSpec.parse("4..8"),
                memory=Range[Memory](min=Memory.parse("8GB"), max=Memory.parse("32GB")),
                gpu=None,
            )
        )
        shared_offer_requirements = Requirements(
            resources=ResourcesSpec(
                cpu=CPUSpec.parse("2"),
                memory=Range[Memory](min=Memory.parse("3GB"), max=None),
                gpu=None,
            )
        )
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            backend_mock = Mock()
            backend_mock.TYPE = BackendType.DSTACK
            backend_mock.compute.return_value = Mock(spec=ComputeMockSpec)
            container_offer = get_instance_offer_with_availability(
                backend=BackendType.KUBERNETES,
                region="",
                instance_type="container-offer",
                cpu_count=4,
                memory_gib=8,
            )
            vm_offer = get_instance_offer_with_availability(
                backend=BackendType.SEEWEB,
                instance_type="vm-offer",
                cpu_count=4,
                memory_gib=8,
            )
            backend_mock.compute.return_value.get_offers.return_value = [
                container_offer,
                vm_offer,
            ]
            m.return_value = [backend_mock]
            res = await get_offers_by_requirements(
                project=Mock(),
                profile=profile,
                requirements=requirements,
                shared_offer_requirements=shared_offer_requirements,
                blocks="auto",
                max_offers=1,
            )

            assert [
                (backend, offer.backend, offer.instance.name, offer.blocks, offer.total_blocks)
                for backend, offer in res
            ] == [(backend_mock, BackendType.SEEWEB, "vm-offer", 2, 4)]
