"""Test backward compatibility for replica_groups with older servers."""

from dstack._internal.core.compatibility.runs import get_get_plan_excludes, get_run_spec_excludes
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.repos import LocalRunRepoData
from dstack._internal.core.models.runs import RunSpec
from dstack._internal.server.schemas.runs import GetRunPlanRequest


class TestReplicaGroupsBackwardCompatibility:
    """Test that replica_groups field is excluded when None for backward compatibility."""

    def test_replica_groups_excluded_when_none(self):
        """replica_groups should be excluded from JSON when None."""
        config = ServiceConfiguration(
            type="service",
            port=8000,
            commands=["echo test"],
            replicas={"min": 1, "max": 1},
        )

        run_spec = RunSpec(
            run_name="test-run",
            repo_id="test-repo",
            repo_data=LocalRunRepoData(repo_dir="/tmp"),
            configuration=config,
            profile=None,
        )

        # Get excludes
        excludes = get_run_spec_excludes(run_spec)

        # replica_groups should be in excludes
        assert "configuration" in excludes
        assert "replica_groups" in excludes["configuration"]
        assert excludes["configuration"]["replica_groups"] is True

    def test_replica_groups_not_excluded_when_set(self):
        """replica_groups should NOT be excluded when set."""
        config = ServiceConfiguration(
            type="service",
            port=8000,
            commands=["echo test"],
            replica_groups=[
                {
                    "name": "gpu-group",
                    "replicas": "1",
                    "resources": {"gpu": {"name": "A100"}},
                }
            ],
            scaling={"metric": "rps", "target": 10},
        )

        run_spec = RunSpec(
            run_name="test-run",
            repo_id="test-repo",
            repo_data=LocalRunRepoData(repo_dir="/tmp"),
            configuration=config,
            profile=None,
        )

        # Get excludes
        excludes = get_run_spec_excludes(run_spec)

        # replica_groups should NOT be in excludes (or be False)
        if "configuration" in excludes and "replica_groups" in excludes["configuration"]:
            assert excludes["configuration"]["replica_groups"] is not True

    def test_get_plan_request_serialization_without_replica_groups(self):
        """GetRunPlanRequest should not include replica_groups in JSON when None."""
        config = ServiceConfiguration(
            type="service",
            port=8000,
            commands=["echo test"],
            replicas={"min": 1, "max": 1},
        )

        run_spec = RunSpec(
            run_name="test-run",
            repo_id="test-repo",
            repo_data=LocalRunRepoData(repo_dir="/tmp"),
            configuration=config,
            profile=None,
        )

        request = GetRunPlanRequest(run_spec=run_spec, max_offers=None)
        excludes = get_get_plan_excludes(request)

        # Serialize with excludes
        json_str = request.json(exclude=excludes)

        # replica_groups should not appear in JSON
        assert "replica_groups" not in json_str

    def test_get_plan_request_serialization_with_replica_groups(self):
        """GetRunPlanRequest should include replica_groups in JSON when set."""
        config = ServiceConfiguration(
            type="service",
            port=8000,
            commands=["echo test"],
            replica_groups=[
                {
                    "name": "gpu-group",
                    "replicas": "1",
                    "resources": {"gpu": {"name": "A100"}},
                }
            ],
            scaling={"metric": "rps", "target": 10},
        )

        run_spec = RunSpec(
            run_name="test-run",
            repo_id="test-repo",
            repo_data=LocalRunRepoData(repo_dir="/tmp"),
            configuration=config,
            profile=None,
        )

        request = GetRunPlanRequest(run_spec=run_spec, max_offers=None)
        excludes = get_get_plan_excludes(request)

        # Serialize with excludes
        json_str = request.json(exclude=excludes)

        # replica_groups SHOULD appear in JSON
        assert "replica_groups" in json_str
        assert "gpu-group" in json_str
