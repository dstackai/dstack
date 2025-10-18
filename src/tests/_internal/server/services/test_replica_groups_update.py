"""Tests for updating services with replica groups."""

from pydantic import parse_obj_as

from dstack._internal.core.models.configurations import (
    ReplicaGroup,
    ScalingSpec,
    ServiceConfiguration,
)
from dstack._internal.core.models.profiles import Profile, SpotPolicy
from dstack._internal.core.models.resources import GPUSpec, Range, ResourcesSpec
from dstack._internal.core.models.runs import RunSpec
from dstack._internal.server.services.runs import _check_can_update_run_spec


def test_can_update_from_replicas_to_replica_groups():
    """Test that we can update a service from simple replicas to replica_groups."""
    # Old config with simple replicas
    old_config = ServiceConfiguration(
        commands=["echo hello"],
        port=8000,
        replicas=2,
        resources=ResourcesSpec(gpu=parse_obj_as(GPUSpec, "H100:1")),
    )

    old_run_spec = RunSpec(
        run_name="test-run",
        repo_id="test-repo",
        repo_data={"repo_type": "local", "repo_dir": "/repo"},
        configuration_path="dstack.yaml",
        configuration=old_config,
        profile=Profile(name="test-profile"),
        ssh_key_pub="ssh_key",
    )

    # New config with replica_groups
    new_config = ServiceConfiguration(
        commands=["echo hello"],
        port=8000,
        replica_groups=[
            ReplicaGroup(
                name="h100-group",
                replicas=parse_obj_as(Range[int], 1),
                resources=ResourcesSpec(gpu=parse_obj_as(GPUSpec, "H100:1")),
                regions=["us-east-1"],
            ),
            ReplicaGroup(
                name="rtx5090-group",
                replicas=parse_obj_as(Range[int], "0..3"),
                resources=ResourcesSpec(gpu=parse_obj_as(GPUSpec, "RTX5090:1")),
                regions=["jp-japan"],
            ),
        ],
        scaling=ScalingSpec(metric="rps", target=10),
    )

    new_run_spec = RunSpec(
        run_name="test-run",
        repo_id="test-repo",
        repo_data={"repo_type": "local", "repo_dir": "/repo"},
        configuration_path="dstack.yaml",
        configuration=new_config,
        profile=Profile(name="test-profile"),
        ssh_key_pub="ssh_key",
    )

    # This should NOT raise an error
    _check_can_update_run_spec(old_run_spec, new_run_spec)


def test_can_update_from_replica_groups_to_replicas():
    """Test that we can update a service from replica_groups back to simple replicas."""
    # Old config with replica_groups
    old_config = ServiceConfiguration(
        commands=["echo hello"],
        port=8000,
        replica_groups=[
            ReplicaGroup(
                name="h100-group",
                replicas=parse_obj_as(Range[int], 1),
                resources=ResourcesSpec(gpu=parse_obj_as(GPUSpec, "H100:1")),
            ),
        ],
    )

    old_run_spec = RunSpec(
        run_name="test-run",
        repo_id="test-repo",
        repo_data={"repo_type": "local", "repo_dir": "/repo"},
        configuration_path="dstack.yaml",
        configuration=old_config,
        profile=Profile(name="test-profile"),
        ssh_key_pub="ssh_key",
    )

    # New config with simple replicas
    new_config = ServiceConfiguration(
        commands=["echo hello"],
        port=8000,
        replicas=2,
        resources=ResourcesSpec(gpu=parse_obj_as(GPUSpec, "A100:1")),
    )

    new_run_spec = RunSpec(
        run_name="test-run",
        repo_id="test-repo",
        repo_data={"repo_type": "local", "repo_dir": "/repo"},
        configuration_path="dstack.yaml",
        configuration=new_config,
        profile=Profile(name="test-profile"),
        ssh_key_pub="ssh_key",
    )

    # This should NOT raise an error
    _check_can_update_run_spec(old_run_spec, new_run_spec)


def test_can_update_replica_groups():
    """Test that we can update replica_groups in place."""
    # Old config
    old_config = ServiceConfiguration(
        commands=["echo hello"],
        port=8000,
        replica_groups=[
            ReplicaGroup(
                name="gpu-group",
                replicas=parse_obj_as(Range[int], "1..3"),
                resources=ResourcesSpec(gpu=parse_obj_as(GPUSpec, "H100:1")),
                regions=["us-east-1"],
            ),
        ],
        scaling=ScalingSpec(metric="rps", target=10),
    )

    old_run_spec = RunSpec(
        run_name="test-run",
        repo_id="test-repo",
        repo_data={"repo_type": "local", "repo_dir": "/repo"},
        configuration_path="dstack.yaml",
        configuration=old_config,
        profile=Profile(name="test-profile"),
        ssh_key_pub="ssh_key",
    )

    # New config with different replica_groups
    new_config = ServiceConfiguration(
        commands=["echo hello"],
        port=8000,
        replica_groups=[
            ReplicaGroup(
                name="gpu-group",
                replicas=parse_obj_as(Range[int], "2..5"),  # Changed range
                resources=ResourcesSpec(gpu=parse_obj_as(GPUSpec, "A100:1")),  # Changed GPU
                regions=["us-west-2"],  # Changed region
                spot_policy=SpotPolicy.SPOT,  # Added spot policy
            ),
        ],
        scaling=ScalingSpec(metric="rps", target=20),  # Changed target
    )

    new_run_spec = RunSpec(
        run_name="test-run",
        repo_id="test-repo",
        repo_data={"repo_type": "local", "repo_dir": "/repo"},
        configuration_path="dstack.yaml",
        configuration=new_config,
        profile=Profile(name="test-profile"),
        ssh_key_pub="ssh_key",
    )

    # This should NOT raise an error (replica_groups + resources + scaling are all updatable)
    _check_can_update_run_spec(old_run_spec, new_run_spec)
