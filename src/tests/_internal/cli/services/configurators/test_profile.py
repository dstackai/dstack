import argparse
from typing import List, Tuple

import pytest

from dstack._internal.cli.services.configurators.profile import (
    apply_profile_args,
    gpu_spec,
    register_profile_args,
)
from dstack._internal.core.models.profiles import (
    Profile,
    ProfileGPU,
    ProfileResources,
    ProfileRetryPolicy,
    SpotPolicy,
)


class TestGPUSpec:
    def test_name(self):
        assert gpu_spec("A100") == {"name": "A100"}

    def test_count(self):
        assert gpu_spec("2") == {"count": "2"}

    def test_memory_gb(self):
        assert gpu_spec("2GB") == {"memory": "2GB"}

    def test_memory_mb(self):
        assert gpu_spec("2MB") == {"memory": "2MB"}

    def test_mixed(self):
        assert gpu_spec("A100:2:2GB") == {"name": "A100", "count": "2", "memory": "2GB"}

    def test_reorder(self):
        assert (
            gpu_spec("2:2GB:A100")
            == gpu_spec("A100:2:2GB")
            == {"name": "A100", "count": "2", "memory": "2GB"}
        )

    def test_empty(self):
        with pytest.raises(ValueError):
            gpu_spec("")

    def test_duplicate(self):
        with pytest.raises(ValueError):
            gpu_spec("A100:A100")

    def test_invalid_token(self):
        with pytest.raises(ValueError):
            gpu_spec("-1")
        with pytest.raises(ValueError):
            gpu_spec("1TB")


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

    def test_gpu(self):
        profile = Profile(name="test")
        modified, _ = apply_args(profile, ["--gpu", "A100:2:2GB"])
        profile.resources.gpu = ProfileGPU(name="A100", count=2, memory="2GB")
        assert profile.dict() == modified.dict()

    def test_gpu_merge(self):
        profile = Profile(
            name="test",
            resources=ProfileResources(
                gpu=ProfileGPU(name="A100", count=1),
            ),
        )
        modified, _ = apply_args(profile, ["--gpu", "A100:4"])
        profile.resources.gpu.count = 4
        assert profile.dict() == modified.dict()

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
        modified, _ = apply_args(profile, ["--retry"])
        profile.retry_policy.retry = True
        assert profile.dict() == modified.dict()

    def test_no_retry(self):
        profile = Profile(name="test", retry_policy=ProfileRetryPolicy(retry=True, limit=3600))
        modified, _ = apply_args(profile, ["--no-retry"])
        profile.retry_policy.retry = False
        assert profile.dict() == modified.dict()

    def test_retry_limit(self):
        profile = Profile(name="test")
        modified, _ = apply_args(profile, ["--retry-limit", "1h"])
        profile.retry_policy.retry = True
        profile.retry_policy.limit = 3600
        assert profile.dict() == modified.dict()


def apply_args(profile: Profile, args: List[str]) -> Tuple[Profile, argparse.Namespace]:
    parser = argparse.ArgumentParser()
    register_profile_args(parser)
    profile = profile.copy(deep=True)  # to avoid modifying the original profile
    args = parser.parse_args(args)
    apply_profile_args(args, profile)
    return profile, args
