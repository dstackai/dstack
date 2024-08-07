import argparse
from typing import List, Tuple

from dstack._internal.cli.services.profile import (
    apply_profile_args,
    register_profile_args,
)
from dstack._internal.core.models.profiles import Profile, ProfileRetryPolicy, SpotPolicy


class TestProfileArgs:
    def test_empty(self):
        profile = Profile(name="test")
        modified, _ = apply_args(profile, [])
        assert profile.dict() == modified.dict()

    def test_profile_name(self):
        profile = Profile(name="test")
        modified, args = apply_args(profile, ["--profile", "test2"])
        assert profile.dict() == modified.dict()
        assert args.profile == "test2"

    def test_max_price(self):
        profile = Profile(name="test")
        modified, _ = apply_args(profile, ["--max-price", "0.5"])
        profile.max_price = 0.5
        assert profile.dict() == modified.dict()

    def test_max_duration(self):
        profile = Profile(name="test")
        modified, _ = apply_args(profile, ["--max-duration", "1h"])
        profile.max_duration = 3600
        assert profile.dict() == modified.dict()

    def test_backends(self):
        profile = Profile(name="test")
        modified, _ = apply_args(profile, ["-b", "local", "--backend", "aws"])
        profile.backends = ["local", "aws"]
        assert profile.dict() == modified.dict()

    def test_spot_policy_spot(self):
        profile = Profile(name="test")
        modified, _ = apply_args(profile, ["--spot"])
        profile.spot_policy = SpotPolicy.SPOT
        assert profile.dict() == modified.dict()

    def test_spot_policy_on_demand(self):
        profile = Profile(name="test")
        modified, _ = apply_args(profile, ["--on-demand"])
        profile.spot_policy = SpotPolicy.ONDEMAND
        assert profile.dict() == modified.dict()

    def test_retry(self):
        profile = Profile(name="test")
        profile.retry_policy = ProfileRetryPolicy(retry=True)
        modified, _ = apply_args(profile, ["--retry"])
        assert profile.dict() == modified.dict()

    def test_no_retry(self):
        profile = Profile(name="test", retry_policy=ProfileRetryPolicy(retry=True, duration=3600))
        modified, _ = apply_args(profile, ["--no-retry"])
        profile.retry_policy.retry = False
        assert profile.dict() == modified.dict()

    def test_retry_duration(self):
        profile = Profile(name="test")
        modified, _ = apply_args(profile, ["--retry-duration", "1h"])
        profile.retry_policy = ProfileRetryPolicy(retry=True, duration=3600)
        assert profile.dict() == modified.dict()


def apply_args(profile: Profile, args: List[str]) -> Tuple[Profile, argparse.Namespace]:
    parser = argparse.ArgumentParser()
    register_profile_args(parser)
    profile = profile.copy(deep=True)  # to avoid modifying the original profile
    args = parser.parse_args(args)
    apply_profile_args(args, profile)
    return profile, args
