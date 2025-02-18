from unittest.mock import Mock, patch

import pytest

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.profiles import Profile
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.runs import Requirements
from dstack._internal.server.services.offers import get_offers_by_requirements
from dstack._internal.server.testing.common import (
    get_instance_offer_with_availability,
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
            aws_backend_mock.compute.return_value.get_offers_cached.return_value = [aws_offer]
            runpod_backend_mock = Mock()
            runpod_backend_mock.TYPE = BackendType.RUNPOD
            runpod_offer = get_instance_offer_with_availability(backend=BackendType.RUNPOD)
            runpod_backend_mock.compute.return_value.get_offers_cached.return_value = [
                runpod_offer
            ]
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
            aws_backend_mock.compute.return_value.get_offers_cached.return_value = [aws_offer]
            runpod_backend_mock = Mock()
            runpod_backend_mock.TYPE = BackendType.RUNPOD
            runpod_offer = get_instance_offer_with_availability(backend=BackendType.RUNPOD)
            runpod_backend_mock.compute.return_value.get_offers_cached.return_value = [
                runpod_offer
            ]
            m.return_value = [aws_backend_mock, runpod_backend_mock]
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
            aws_backend_mock.compute.return_value.get_offers_cached.return_value = [aws_offer]
            runpod_backend_mock = Mock()
            runpod_backend_mock.TYPE = BackendType.RUNPOD
            runpod_offer1 = get_instance_offer_with_availability(
                backend=BackendType.RUNPOD, region="eu"
            )
            runpod_offer2 = get_instance_offer_with_availability(
                backend=BackendType.RUNPOD, region="us"
            )
            runpod_backend_mock.compute.return_value.get_offers_cached.return_value = [
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
            expected_aws_offer3 = aws_offer3.copy()
            expected_aws_offer3.availability_zones = ["az3"]
            aws_offer4 = get_instance_offer_with_availability(
                backend=BackendType.AWS, availability_zones=None
            )
            aws_backend_mock.compute.return_value.get_offers_cached.return_value = [
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
    async def test_returns_no_offers_for_multinode_instance_mounts_and_non_multinode_backend(self):
        # Regression test for https://github.com/dstackai/dstack/issues/2211
        profile = Profile(name="test", backends=[BackendType.RUNPOD])
        requirements = Requirements(resources=ResourcesSpec())
        with patch("dstack._internal.server.services.backends.get_project_backends") as m:
            aws_backend_mock = Mock()
            aws_backend_mock.TYPE = BackendType.AWS
            aws_offer = get_instance_offer_with_availability(backend=BackendType.AWS)
            aws_backend_mock.compute.return_value.get_offers_cached.return_value = [aws_offer]
            runpod_backend_mock = Mock()
            runpod_backend_mock.TYPE = BackendType.RUNPOD
            runpod_offer = get_instance_offer_with_availability(backend=BackendType.RUNPOD)
            runpod_backend_mock.compute.return_value.get_offers_cached.return_value = [
                runpod_offer
            ]
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
