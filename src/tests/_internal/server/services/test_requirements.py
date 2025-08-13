from typing import Optional

import pytest

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.profiles import SpotPolicy
from dstack._internal.server.services.requirements import Profile, combine_fleet_and_run_profiles


class TestCombineFleetAndRunProfiles:
    def test_returns_the_same_profile_if_profiles_identical(self):
        profile = Profile(
            backends=[BackendType.AWS],
            regions=["us-west2"],
            availability_zones=None,
            instance_types=None,
            reservation="r-12345",
            spot_policy=SpotPolicy.AUTO,
            idle_duration=3600,
        )
        assert combine_fleet_and_run_profiles(profile, profile) == profile

    @pytest.mark.parametrize(
        argnames=["fleet_profile", "run_profile", "expected_profile"],
        argvalues=[
            pytest.param(
                Profile(),
                Profile(),
                Profile(),
                id="empty_profile",
            ),
            pytest.param(
                Profile(
                    backends=[BackendType.AWS, BackendType.GCP],
                    regions=["eu-west1", "europe-west-4"],
                    instance_types=["instance1"],
                    reservation="r-1",
                    spot_policy=SpotPolicy.AUTO,
                    idle_duration=3600,
                ),
                Profile(
                    backends=[BackendType.GCP, BackendType.RUNPOD],
                    regions=["eu-west2", "europe-west-4"],
                    instance_types=["instance2"],
                    reservation="r-1",
                    spot_policy=SpotPolicy.SPOT,
                    idle_duration=7200,
                ),
                Profile(
                    backends=[BackendType.GCP],
                    regions=["europe-west-4"],
                    instance_types=[],
                    reservation="r-1",
                    spot_policy=SpotPolicy.SPOT,
                    idle_duration=3600,
                ),
                id="compatible_profiles",
            ),
            pytest.param(
                Profile(
                    spot_policy=SpotPolicy.SPOT,
                ),
                Profile(
                    spot_policy=SpotPolicy.ONDEMAND,
                ),
                None,
                id="incompatible_profiles",
            ),
        ],
    )
    def test_combines_profiles(
        self,
        fleet_profile: Profile,
        run_profile: Profile,
        expected_profile: Optional[Profile],
    ):
        assert combine_fleet_and_run_profiles(fleet_profile, run_profile) == expected_profile


class TestIntersectLists:
    # TODO
    pass


class TestCombineIdleDuration:
    # TODO
    pass
