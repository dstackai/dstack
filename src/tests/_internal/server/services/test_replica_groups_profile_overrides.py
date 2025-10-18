"""Tests for replica group profile overrides (regions, spot_policy, etc.)"""

import pytest
from pydantic import parse_obj_as

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.configurations import (
    ReplicaGroup,
    ScalingSpec,
    ServiceConfiguration,
)
from dstack._internal.core.models.profiles import Profile, SpotPolicy
from dstack._internal.core.models.resources import GPUSpec, Range, ResourcesSpec
from dstack._internal.core.models.runs import RunSpec
from dstack._internal.server.services.runs import _get_job_profile

pytestmark = pytest.mark.usefixtures("image_config_mock")


def test_spot_policy_override_per_group():
    """Test that each replica group can have its own spot_policy."""
    # Create a service with different spot policies per group
    config = ServiceConfiguration(
        commands=["echo hello"],
        port=8000,
        replica_groups=[
            ReplicaGroup(
                name="on-demand-group",
                replicas=parse_obj_as(Range[int], 1),
                resources=ResourcesSpec(gpu=parse_obj_as(GPUSpec, "H100:1")),
                spot_policy=SpotPolicy.ONDEMAND,
            ),
            ReplicaGroup(
                name="spot-group",
                replicas=parse_obj_as(Range[int], 1),
                resources=ResourcesSpec(gpu=parse_obj_as(GPUSpec, "RTX5090:1")),
                spot_policy=SpotPolicy.SPOT,
            ),
            ReplicaGroup(
                name="auto-group",
                replicas=parse_obj_as(Range[int], 1),
                resources=ResourcesSpec(gpu=parse_obj_as(GPUSpec, "A100:1")),
                spot_policy=SpotPolicy.AUTO,
            ),
        ],
        scaling=ScalingSpec(metric="rps", target=10),
    )

    profile = Profile(name="test-profile", spot_policy=SpotPolicy.AUTO)  # base policy
    run_spec = RunSpec(
        run_name="test-run",
        repo_id="test-repo",
        repo_data={"repo_type": "local", "repo_dir": "/repo"},
        configuration_path="dstack.yaml",
        configuration=config,
        profile=profile,
        ssh_key_pub="ssh_key",
    )

    # Test on-demand group
    on_demand_profile = _get_job_profile(run_spec, "on-demand-group")
    assert on_demand_profile.spot_policy == SpotPolicy.ONDEMAND

    # Test spot group
    spot_profile = _get_job_profile(run_spec, "spot-group")
    assert spot_profile.spot_policy == SpotPolicy.SPOT

    # Test auto group
    auto_profile = _get_job_profile(run_spec, "auto-group")
    assert auto_profile.spot_policy == SpotPolicy.AUTO

    # Test legacy (no group) uses base profile
    legacy_profile = _get_job_profile(run_spec, None)
    assert legacy_profile.spot_policy == SpotPolicy.AUTO


def test_regions_override_per_group():
    """Test that each replica group can have its own regions."""
    config = ServiceConfiguration(
        commands=["echo hello"],
        port=8000,
        replica_groups=[
            ReplicaGroup(
                name="us-group",
                replicas=parse_obj_as(Range[int], 1),
                resources=ResourcesSpec(gpu=parse_obj_as(GPUSpec, "H100:1")),
                regions=["us-east-1", "us-west-2"],
            ),
            ReplicaGroup(
                name="eu-group",
                replicas=parse_obj_as(Range[int], 1),
                resources=ResourcesSpec(gpu=parse_obj_as(GPUSpec, "RTX5090:1")),
                regions=["eu-west-1", "eu-central-1"],
            ),
            ReplicaGroup(
                name="asia-group",
                replicas=parse_obj_as(Range[int], 1),
                resources=ResourcesSpec(gpu=parse_obj_as(GPUSpec, "A100:1")),
                regions=["ap-northeast-1"],
            ),
        ],
        scaling=ScalingSpec(metric="rps", target=10),
    )

    profile = Profile(name="test-profile", regions=["us-east-1"])  # base regions
    run_spec = RunSpec(
        run_name="test-run",
        repo_id="test-repo",
        repo_data={"repo_type": "local", "repo_dir": "/repo"},
        configuration_path="dstack.yaml",
        configuration=config,
        profile=profile,
        ssh_key_pub="ssh_key",
    )

    # Test US group
    us_profile = _get_job_profile(run_spec, "us-group")
    assert us_profile.regions == ["us-east-1", "us-west-2"]

    # Test EU group
    eu_profile = _get_job_profile(run_spec, "eu-group")
    assert eu_profile.regions == ["eu-west-1", "eu-central-1"]

    # Test Asia group
    asia_profile = _get_job_profile(run_spec, "asia-group")
    assert asia_profile.regions == ["ap-northeast-1"]

    # Test legacy (no group) uses base profile
    legacy_profile = _get_job_profile(run_spec, None)
    assert legacy_profile.regions == ["us-east-1"]


def test_backends_override_per_group():
    """Test that each replica group can have its own backends."""
    config = ServiceConfiguration(
        commands=["echo hello"],
        port=8000,
        replica_groups=[
            ReplicaGroup(
                name="aws-group",
                replicas=parse_obj_as(Range[int], 1),
                resources=ResourcesSpec(gpu=parse_obj_as(GPUSpec, "H100:1")),
                backends=[BackendType.AWS],
            ),
            ReplicaGroup(
                name="vastai-group",
                replicas=parse_obj_as(Range[int], 1),
                resources=ResourcesSpec(gpu=parse_obj_as(GPUSpec, "RTX5090:1")),
                backends=[BackendType.VASTAI],
            ),
        ],
        scaling=ScalingSpec(metric="rps", target=10),
    )

    profile = Profile(
        name="test-profile",
        backends=[BackendType.AWS, BackendType.GCP],  # base backends
    )
    run_spec = RunSpec(
        run_name="test-run",
        repo_id="test-repo",
        repo_data={"repo_type": "local", "repo_dir": "/repo"},
        configuration_path="dstack.yaml",
        configuration=config,
        profile=profile,
        ssh_key_pub="ssh_key",
    )

    # Test AWS group
    aws_profile = _get_job_profile(run_spec, "aws-group")
    assert aws_profile.backends == [BackendType.AWS]

    # Test VastAI group
    vastai_profile = _get_job_profile(run_spec, "vastai-group")
    assert vastai_profile.backends == [BackendType.VASTAI]

    # Test legacy (no group) uses base profile
    legacy_profile = _get_job_profile(run_spec, None)
    assert legacy_profile.backends == [BackendType.AWS, BackendType.GCP]


def test_multiple_profile_overrides_per_group():
    """Test that a replica group can override multiple profile parameters at once."""
    config = ServiceConfiguration(
        commands=["echo hello"],
        port=8000,
        replica_groups=[
            ReplicaGroup(
                name="specialized-group",
                replicas=parse_obj_as(Range[int], 1),
                resources=ResourcesSpec(gpu=parse_obj_as(GPUSpec, "H100:1")),
                regions=["us-west-2"],
                backends=[BackendType.AWS],
                spot_policy=SpotPolicy.ONDEMAND,
                max_price=5.0,
            ),
        ],
        scaling=ScalingSpec(metric="rps", target=10),
    )

    profile = Profile(
        name="test-profile",
        regions=["us-east-1"],
        backends=[BackendType.GCP],
        spot_policy=SpotPolicy.SPOT,
        max_price=1.0,
    )
    run_spec = RunSpec(
        run_name="test-run",
        repo_id="test-repo",
        repo_data={"repo_type": "local", "repo_dir": "/repo"},
        configuration_path="dstack.yaml",
        configuration=config,
        profile=profile,
        ssh_key_pub="ssh_key",
    )

    specialized_profile = _get_job_profile(run_spec, "specialized-group")
    assert specialized_profile.regions == ["us-west-2"]
    assert specialized_profile.backends == [BackendType.AWS]
    assert specialized_profile.spot_policy == SpotPolicy.ONDEMAND
    assert specialized_profile.max_price == 5.0


def test_partial_profile_override():
    """Test that only specified profile parameters are overridden, others inherit from base."""
    config = ServiceConfiguration(
        commands=["echo hello"],
        port=8000,
        replica_groups=[
            ReplicaGroup(
                name="partial-group",
                replicas=parse_obj_as(Range[int], 1),
                resources=ResourcesSpec(gpu=parse_obj_as(GPUSpec, "H100:1")),
                regions=["us-west-2"],  # Only override regions
                # spot_policy, backends, max_price should inherit from base
            ),
        ],
        scaling=ScalingSpec(metric="rps", target=10),
    )

    profile = Profile(
        name="test-profile",
        regions=["us-east-1"],
        backends=[BackendType.GCP, BackendType.AWS],
        spot_policy=SpotPolicy.SPOT,
        max_price=2.5,
    )
    run_spec = RunSpec(
        run_name="test-run",
        repo_id="test-repo",
        repo_data={"repo_type": "local", "repo_dir": "/repo"},
        configuration_path="dstack.yaml",
        configuration=config,
        profile=profile,
        ssh_key_pub="ssh_key",
    )

    partial_profile = _get_job_profile(run_spec, "partial-group")
    # Overridden
    assert partial_profile.regions == ["us-west-2"]
    # Inherited from base
    assert partial_profile.backends == [BackendType.GCP, BackendType.AWS]
    assert partial_profile.spot_policy == SpotPolicy.SPOT
    assert partial_profile.max_price == 2.5
